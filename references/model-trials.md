# 用真实模型产物改进 skill

只在使用者要求多模型试用、行为评测或维护本 skill 时读取。普通论文任务不自动增加评测、模型调用或费用；公开研发夹具使用匿名合成材料。用户已授权的真实赛题试用在仓库外私有研究目录保存完整输入与记录，不改写既有论文或把实际赛题资料加入公开仓库。

## 有限的一轮改进

1. 先确定实际可用的工具、套餐端点、模型名称、材料授权和调用次数。本轮可以采用“基线两题 → 查实失败 → 局部修订 → 新数据复测”，不是无限自改或后台定时任务。套餐名称不等于模型名称；最新官方文档与实际鉴权共同决定可用路线。失败的鉴权不计作模型能力差。
2. 冻结匿名题目、选用的 skill 文本、输入数据和验收依据。不同路线获得相同任务和相同资料，不把参考答案、其他路线结果或评审意见混入基线提示词。记录模型调用名、编程工具版本、推理选项、时间、用量和原始产物。结果文件用新目录，保留输入和输出哈希。
   使用真实赛题时，给每条路线完整原始 PDF、题内附录、全部附件/工作表、原始输出样表和逐问要求映射；按[材料合同](case-materials.md)核对准备及实际读取证据。旧论文、已填结果、参考求解代码与参考答案不进入独立基线，题意概述不能替代完整原始输入。
   冻结本阶段必要规范名单并核对实际送达。题意/建模阶段除本项目 `SKILL.md`，还须读取 `references/case-materials.md`、`references/evidence-and-writing.md`、所选上游分析入口及其引用的共享规范所需章节。原规则已经包含的防错要求未被模型实际读取时，先修阶段交接/harness，不把它写成规范原本缺失。
3. 要求交付本阶段的实际产物：建模报告、计算程序与结果、图源或论文及题面指定材料。不要用“请评价本 skill”或模型自称已经运行、已经正确作为效果证据。无工具任务和实际工具执行分别记录，不能互称；全文只在其依赖阶段验收后进入完整实例判断。
4. 先用可信计算核对数值与约束，再逐段核对科学含义、摘要和 memo/letter。检查器只认可它实际检测的项目；代码存在不等于代码运行，LaTeX 字符串存在不等于公式已编译。外部生成的程序和 TeX 先审查，再在不含密钥的隔离目录运行或编译。
5. 根据查实错误做局部修订。例如漏掉切换点上的并列最优方案、把识别集合叫成置信区间、Summary 的建议与情景结果冲突。修订应改善相应决策，不堆通用禁令，不给所有问题强加该案例的模型、单位、题数或输出格式。
6. 保留基线输入，用独立的新参数或任务复测；如果要判断更新效果，再以同一旧任务做对照重跑。新任务和旧任务难度不同，不能直接把得分差归因于 skill 更新。记录未修复项、失败与未执行项，不把小任务表现外推成完整论文水平或获奖概率。

响应截断时按实际阶段拆分任务，冻结每阶段输入/skill及其字节哈希。不要拼接截断内容冒充完整交付；[merge_trial_stages.py](../scripts/merge_trial_stages.py) 只合并同一任务、上下文、模型和客户端的成功阶段，保留原始答案并记录外层代码围栏的移除。更换客户端/协议或模型版本须单列，不能把速度变化归因于skill改进。

## 完整长稿实例

完整实例先核对输入齐全、接收模型能读取原件及页图、实际程序写入/运行与编译能力可用。材料存在与真实读取分别记录；原 DOC 被保存但未解析时说明具体缺口。只有摘要文本、局部题面或一部分工作表的试用不能记录为完整赛题测试。

先冻结数据合同和每张表的时间范围：日号/样本ID对齐，验证选择与测试评价分开；不能用数组位置暗替日期，或把验证网格写成测试表。先实际运行程序并核对完整结果，再把经过核对的数据送入写作阶段。各阶段保留同一题目、来源与实际模型名；不把另一模型段落拼进来当原模型完成。

`prepare_full_paper_case.py` 提供匿名合成物流夹具；`complete_case_reference.py` 是独立核算，不能把参考答案放进基线提示词。`check_complete_case.py --reviewed-source` 核对此夹具的预测、政策、逐日收支、完整网格和敏感性，拒绝重复日号。它不是通用物流求解器或OS沙箱；先读源，再运行不含凭据的子进程。

本轮“20 页以上及全部支撑材料”是用户选择的实例合同，按约定 PDF 范围检验至少 21 页；其他任务另定范围，不自动继承此下限或过往 31 页上限。验收覆盖完整逐问求解、实际结果、可编辑论文源、图源、PDF 与所需支撑包。不能通过重复、放大间距或强制空页实现页数。原始错误、模型修订、宿主修订及最终结果分别留档。

宿主装配/扩写原型保留在内部 QA：其中的固定章节、特定字符串修正和补充科学段落是实验干预，不是生产写作入口，也不计为外部模型完成。模型没有调用工具时，宿主承担的求解运行、绘图、模板选择、字体选择、编译与修订都要单列；源码通过独立核算仍不证明模型能操作项目或完成长稿。

检查项目是否易用时，优先做真实工具任务：代理自己读取入口、选择模板/字体/图件格式、运行项目检查，并针对返回的错误修订。只把skill粘到提示词、禁用全部工具后人工组稿，不能称作代理会使用项目。纯文本试用继续作为独立能力试验，不与项目操作成绩混算。见[渲染合同](rendering-contract.md)。

并发OpenCode进程用各自的XDG数据/缓存目录，避免全局SQLite锁冲突。配置推理档位时记录实际请求选项与用量；推理占满额度导致length也属于不完整会话，不能只看退出码。客户端锁错误、来源编码/格式错误与解题错误分开判断。局部重试用新目录和明确停止条件。

## 完整材料的只读试验

[`prepare_case_materials.py`](../scripts/prepare_case_materials.py)先生成仓库外的完整材料包；[`case_materials_server.py`](../scripts/case_materials_server.py)以 `--materials` 指向它，按需用 `--audit-log` 保存新的私有读取日志。可选 `--transcript` 指向已存在的 UTF-8 题面/公式转录，作为与原 PDF/页图分开的宿主来源材料，不能夹带参考解答或称为自动核验的公式。接口提供原题逐页 PNG、完整提取文本、全部 XLSX 工作表 CSV/单元格记录、原模板和补充文本。DOC/DOCX等原件保留及其未覆盖解析状态继续可见，不能把材料库的复制成功称为全自动文档读取。

模型先发现工具，再核对清单、逐问要求、完整页图、所有表格与模板。文本按返回的截断/后续范围继续读取，最后获取 `material_read_receipt`。收据记录实际返回给该模型的行范围与页图，不证明理解公式、判断数据质量或已经求解。提示词、模型自述和工具次数不替代完整覆盖记录。

分析阶段将题面要求分为正文抽样范围和完整输出范围，形成给代码阶段的独立实现口径；对应防错规则见[逐问证据链](evidence-and-writing.md#逐问证据链)，不延后到写作才检查。宿主可用只读接口的重复 `--required-project-file` 声明必要项目/上游规则，收据中的 `all_required_project_text_supplied` 与材料的 `all_required_text_supplied` 分开判断。规范文件存在、已登记或模型读过 `SKILL.md` 均不证明必要阶段引用已读完；未声明规范名单也不形成阶段规范完整性的证据。各项覆盖仍只说明内容已返回，不是理解/解答合格。

三种会话模式分别验收：

| 模式 | 当前工具范围 | 合理验收范围 |
| --- | --- | --- |
| `text-only` | 模型工具禁用 | 实际返回的文本/机读答复，宿主执行另计 |
| `case-materials-task` | 一个只读 `case_materials` MCP，其余工具 deny | 完整材料可访问性、实际返回范围、解析缺口与题意核对报告；不执行求解或编译 |
| `project-tool-task` | 一个受限 `paper_project` MCP，其余工具 deny | 已准备 Typst 项目的字体、同源图件、声明的摘要结构与实际编译检查；不表示可运行任意逐问求解 |

完整求解至论文交付需要另有实际可用的程序/数据/图件写入、求解运行和完整编译验收能力。没有这些能力时，按本次接口能完成的阶段交付，不把只读材料会话或局部排版任务写成全题完成。不同阶段可接续，但保留各自的输入、模型、工具状态和产物责任。

## 真实项目工具试验

给代理精简任务入口、工作区、当前阶段的输入/输出范围和实际可用工具。第一步发现能力并读取本技能与对应阶段参考；不要预先粘贴所有上游内容或给出最终修法。每个阶段记录输入哈希、读取轨迹、工具请求/返回、模型决策、输出哈希与验收结果。工具返回只能说明它实际做了什么，例如文件齐全、字体存在或编译完成，各自不能代替科学审查及最终 PDF 视觉核验。

论文渲染试验可用 [`scripts/paper_project_server.py`](../scripts/paper_project_server.py) 提供的受限工作区 MCP；接入前核对启动帮助与实际 `tools/list`。允许代理读取项目/所需 skill 及已登记技能目录内的引用模板/规则、检查渲染、选字体、导出或适配同源图件、处理声明的摘要分页、编译并检查。工具实现与握手通过只证明接口可用；真实模型须实际调用、读回失败、修订源和验收产物后，才记录相应项目行为通过。当前支持的引擎与路径以工具发现结果为准，不据此宣称通用建模求解、全赛制模板或任意 shell 已可用。

工作区先按已选模板准备，且位于技能仓库之外；宿主给定真实的工作区、Typst、字体目录和可选 draw.io 路径，模型不能自行改可执行文件或扩大读写范围。当前受限入口为 `main.typ`，合同为 `rendering-contract.json`，输出为 `main.pdf`。当本次任务要求摘要独立一页时，合同的可选 `summary` 字段示例为：

```json
{"separate_page": true, "max_pages": 1, "heading": "摘要", "body_heading": "研究背景与问题分析"}
```

标题值须来自当前稿和结构合同，不能为匹配示例而改论文标题。分页要求的来源另记在[模板结构记录](template-selection.md#将模板选择落实到结构合同)。代理先读取实际摘要宏，按发现的 `ensure_summary_page` 支持范围处理旧稿，再通过真实 PDF 核验摘要/关键词结束和正文边界；没有摘要合同的任务不自动强加独页要求。

有目的地观察下列行为，记录初版失败及其恢复：

| 输入/现象 | 应发生的行为 | 仍不能据此宣称 |
| --- | --- | --- |
| 请求中文模板字体，环境缺某个 family | 读模板/字体清单，报告缺项，按用户授权选可用替代并核验职责 | PDF 含某字体即整篇字体正确 |
| 图源含 `foreignObject` 或动态 CSS，PDF 黑块/丢字 | 从同一可编辑图源重新导出或生成可移植资产，回编译后看实际 PDF | 原图浏览器预览正确即论文正确 |
| 当前中文稿要求摘要独立一页，PDF 摘要与正文同页 | 读取所选模板的摘要宏与结构来源，修正确实失效的宏调用/分页，核验摘要终点及正文起始 | 字体/SVG 两项通过即完整排版成功 |
| 日号不一致或验证网格冒充测试 | 定位求解代码的数据范围，重新运行独立核算并更新受影响图文 | 宿主手改数字后原模型解题通过 |
| 当前阶段要求程序/图源，模型提前交正文 | 回到声明的阶段输出，完成依赖后再写文 | 文字长度足够即阶段完成 |
| 会话为 `length`/超时，部分文件存在 | 保留原始状态，以明确的接续任务补完并重验 | 客户端退出码为零即完整成功 |

纯文本基线、受工具限制的项目操作、真正逐问求解到论文全交付分别报告。新工具本轮的行为结果只根据实际运行记录填写；空白或未运行项写未验证，不把回归脚本的通过数补成外部模型成绩。

### 冻结现稿的局部回归记录

2026-10-02 的项目工具轮使用宿主已冻结的现稿、计算数据与图源，观察外部代理发现工具、选择可用字体、从同源 draw.io 导出并替换不兼容 SVG、编译及处理摘要结构。这些项目有25/26页产物，页数属于已有正文的局部回归，不能计为模型拿到完整赛题后独立生成的论文。

加入摘要独页检查后的结构轮状态如下；客户端完整结束与约定局部产物通过分开判断：

| 路线 | 会话状态 | 该轮局部产物 | 可记录的结论 |
| --- | --- | --- | --- |
| GLM | 完整返回 | 完成约定的结构/渲染修订与检查 | 此次受限项目任务完成 |
| Kimi | 超时，未形成完整成功会话 | 对应局部产物通过检查 | 已有产物单列，完整会话仍未完成 |
| DeepSeek | 超时，未完成 | 未完成约定交付 | 此次结构任务未完成 |

早先的字体/SVG项目轮与这轮摘要结构任务分开保留，不能用前轮成功替换后轮未完成。这里没有新增模型试验，也没有把真实赛题资料或既有正文发布为示例。完整原题与数据的只读试验、逐问求解和从零论文交付仍需各自实际运行证据；材料接口实现或合成回归通过均不补计为这些模型成绩。

## 密钥与调用材料

凭据只在本机私有文件或进程环境中读取，不进入提示词、源码、CLI 参数、终端输出、公开报告或 Git。截图凭据只做本地识别，字符无法确认时请求使用者在本机更新文件，不能批量猜测密钥。模型生成的代码在不含凭据的环境执行。

按套餐允许的编程工具方式接入；不要把交互套餐改造成自建批量后端，也不要在套餐鉴权失败后自动切到按量付费端点。网络错误和缺少权限单列，保留可用路线继续独立测试。失败重试需有上限和理由，不能凭重试次数制造能力结论。

## 仓库提供的离线夹具

原创建模小题位于 [examples/model-trials/tasks.json](../examples/model-trials/tasks.json)。基线含混合运输成本切换与潜在投票推断；新数据版本包含三方案同时最优和不同的识别边界。这不是 COMAP 官方题目，也不是正式论文。源码 [scripts/model_trial.py](../scripts/model_trial.py) 不联网、不读取密钥、不执行模型代码。

第二版[匿名任务](../examples/model-trials/tasks-v2.json)明确综合排名对象，覆盖空集、全区间、严格边界及纯裁判权重；用 `--tasks` 选择，不改写第一版历史任务。v2运输量允许有说明的 `整数/正整数` 精确分数编码，解析器不执行任意表达式；v1仍采用其数字字段口径。显式空集与漏交字段区分，不能把不可行排名硬截成一个比例。

```sh
python scripts/model_trial.py prepare --tasks examples/model-trials/tasks-v2.json --round clarified --part transport --output qa/trials/transport-01
python scripts/model_trial.py prepare --tasks examples/model-trials/tasks-v2.json --round clarified --part inference --output qa/trials/inference-01
# 每个成功模型会话放在对应阶段目录的model子目录后：
python scripts/merge_trial_stages.py --transport qa/trials/transport-01/model --inference qa/trials/inference-01/model --output qa/trials/assembled-01
python scripts/model_trial.py grade --tasks examples/model-trials/tasks-v2.json --round clarified --answer qa/trials/assembled-01/answer.json --report qa/trials/assembled-01/numeric.json
```

提示词按UTF-8字节写出，记录的prompt哈希与文件相同。早期Windows试用曾出现文本换行转换使两者不同，报告保留运行工具读入文件的实际哈希；不能篡改历史记录掩盖差异。

```sh
python scripts/model_trial.py prepare --round baseline --output qa/trials/baseline-01
# 用使用者授权且套餐支持的编程工具读取生成的 prompt.txt，保存完整 answer.json。
python scripts/model_trial.py grade --round baseline --answer qa/trials/baseline-01/answer.json --report qa/trials/baseline-01/numeric-check.json

# 完成局部修订后生成新上下文快照；模型仍看不到夹具的参考计算。
python scripts/model_trial.py prepare --round holdout --output qa/trials/holdout-01
python scripts/model_trial.py grade --round holdout --answer qa/trials/holdout-01/answer.json --report qa/trials/holdout-01/numeric-check.json
```

`prepare` 拒绝覆盖旧目录，记录 task 和三个实际加载上下文文件的哈希；只将选定轮次数据交给模型。`grade` 独立枚举可行整数方案并检查最优、区间端点、全部切换点及并列最优；投票题核对点识别、严格不等式区间、绝对票数不可识别和无概率依据的区间性质。它还报告字数与产物是否存在，**不自动验证任务分类、英文内容、程序、公式或文献**。夹具字数采用含字母/数字的空白分隔项，千位逗号和连字符不拆词，纯标点不计数；不是赛事通用字数规定。检查器判定与人工明显不符时先检查口径，不能为了提高得分改变正确论文。新报告路径不得与答案相同，旧报告不覆盖。

排名夹具按给定综合得分定义解释“排名”；报告显式记录这一解释，给出边界代回值，错误下界时提供反例。真实题面没有确定排名对象时，先澄清或说明解释，不能用一个未声明的单项排名替换它。少量固定题只覆盖相应行为，不覆盖所有歧义。

## 单次编程工具会话

[scripts/run_codex_trial.py](../scripts/run_codex_trial.py) 使用已安装的 Codex CLI 执行一条显式指定的路线。不会直接请求 API、读取密钥文件、修改全局配置或切换付费端点。凭据须在父进程的路线 `env_key` 环境变量中；示例 [providers.json](../examples/model-trials/providers.json) 只含公开端点、模型名和变量名。模型及套餐支持情况随时间变化，使用前核对官方文档和实际权限： [千问 Token Plan](https://help.aliyun.com/zh/model-studio/token-plan-personal-quick-start)、[火山 Agent Plan](https://docs.volcengine.com/docs/ark/agent-plan-personal-zcode?lang=zh)、[火山 Coding Plan](https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-codex?lang=en)。本轮验证的工具为 Codex CLI 0.144.1；其他版本先检查相关选项是否存在。

```sh
# 环境变量已在本机私有方式加载，不能在命令或文档中填写密钥。
python scripts/run_codex_trial.py --routes examples/model-trials/providers.json --route volcano-agent-plan --prompt qa/trials/baseline-01/prompt.txt --output qa/trials/baseline-01/agent-run --effort low
```

每次只运行一条路线，超时默认480秒，不自动重试；输出目录须是新目录。报告记录输入/答案哈希、请求模型名、推理档位、时长、成功与失败及工具事件数；省略推理全文，脱敏错误信息。调用名不是后台精确模型版本的独立证明，用量是CLI报告而非账单金额。此次任务要求模型只返回文本，CLI使用只读沙箱、工具子进程不继承环境；仍需核查工具事件，不能把提示词当作完整权限隔离。需要程序执行的评测应另设真正隔离的运行环境。

不能比较改变推理档位前后的时间并归因于skill提升；长度截断恢复与模型质量分开记录。不能因机读答复不合法而悄悄修复后给原答复通过成绩；原始文件、人工修复及新的模型重试分别保留。没有真实执行的任务不计作通过。

## 可选客户端与分项验收

MiniMax M Plan 已加入显式地区路线，模型请求名为 `MiniMax-M3.1-Flash-Preview`；首轮实际源码复核与鉴权结果见[2026-10-04记录](../docs/minimax-mplan-20261004.md)。它与人口题科学试用分别统计，不能因正常文本返回就称完成论文或已接网站后端。

[run_opencode_trial.py](../scripts/run_opencode_trial.py) 可使用已安装的 OpenCode，显式选择 `--protocol chat` 或 `--protocol responses` 接入同一授权套餐。默认保留 Chat Completions 的 `@ai-sdk/openai-compatible`；Responses 使用 `@ai-sdk/openai`，不改 endpoint、凭据或模型。当前实际验证版本 1.18.34，原有 Codex 为 0.144.1；需要相应 CLI 选项时先核对帮助。它仅启用所选 provider、以环境变量引用密钥、禁用分享、采用 `--pure`；不保存密钥或改全局配置。默认 `text-only` 禁用全部模型工具并保存 `answer.json`。客户端仍不是 OS 安全沙箱。CLI 终止、答案存在和正常 `stop` 事件共同判断完整会话；`length` 或超时不能记作成功。[官方 provider 说明](https://opencode.ai/docs/providers/)、[CLI 说明](https://opencode.ai/docs/cli/)、[工具权限](https://opencode.ai/docs/permissions/)是兼容配置依据。

火山 Agent Plan 的端点、两种协议与 OpenCode SDK 配置见[官方接入说明](https://docs.volcengine.com/docs/ark/agent-plan-enterprise-opencode?lang=zh)。[路线示例](../examples/model-trials/providers.json)列出本轮实际请求的 DeepSeek、GLM、Kimi Agent Plan 路线，供已获授权且账户确有支持时选择；不替使用者订阅，不从 Coding Plan 自动切换套餐，更不降到普通按量付费端点。套餐限额按真实错误中的重置时间处理，停止无意义重试；接续用保存的同版材料和产物，不重复运行已完成且未变更的阶段。请求模型名不证明后台精确版本。

```sh
python scripts/run_opencode_trial.py --routes examples/model-trials/providers.json --route kimi-coding-plan --prompt qa/trials/transport-01/prompt.txt --output qa/trials/transport-01/model --opencode /path/to/opencode
```

工具模式使用 `--project-tools` 指定已审查的 MCP 启动 JSON。其结构只接受 `name` 与逐项 `command` 数组，`name` 为 `paper_project`、`case_materials` 或 `workflow_project`，每次只选一个；JSON 不含任何凭据。以下是排版项目接口，路径须替换为本机真实路径，`--workspace` 指向仓库外独立准备的项目：

```json
{
  "name": "paper_project",
  "command": [
    "/path/to/python", "-X", "utf8",
    "/path/to/mathmodel-paper-workflow/scripts/paper_project_server.py",
    "--workspace", "/path/to/isolated-project",
    "--compiler", "/path/to/typst",
    "--font-dir", "/path/to/fonts",
    "--drawio", "/path/to/drawio"
  ]
}
```

将上述启动配置保存为本次的 `project-tools.json` 后，按授权路线单次运行：

```sh
python scripts/run_opencode_trial.py --routes examples/model-trials/providers.json --route kimi-coding-plan --prompt /path/to/project-task.txt --output qa/trials/project-01 --project-tools /path/to/project-tools.json --effort low
```

材料接口的启动 JSON 和命令见[完整材料交接](case-materials.md#给其他-ai-的只读入口)，使用 `--materials` 指向完整材料包。[完整项目试用接口](workflow-project-trials.md)另外允许模型写入自己的代码与材料，并仅执行宿主审阅批准的完整代码树。运行器按所选接口只允许其 `*_` 工具前缀，其他工具保持 `deny`；报告记录 `selected_tool_interface`，材料模式为 `case-materials-task`，排版模式为 `project-tool-task`，完整项目为 `workflow-project-task`。保存 `answer.txt`，不把工具任务最终说明当成 `answer.json` 的解题数据。

`--effort low` 可选，报告标记为客户端配置，不能保证 provider 内部推理档位。`successful_session` 只表示客户端完整返回，不能表示项目通过。文本中的 `<seed:tool_call>` 等调用样式且没有真实工具事件时，会标为 `unexecuted_tool_intent`，`answer_delivery_valid=false`，保留原答复但不计为完成调用；该检测是列明格式的启发式筛查。`task_accepted` 始终待独立任务验收，不由客户端成功自动赋真。排版任务还须检查工作区 `project-tool-events.jsonl` 的实际读取/执行/错误/修订记录及最终检查报告和 PDF，材料任务须核对完整文件清单及读回范围收据。工具事件数本身不证明使用正确，同一版产物才能参与验收。

取得完整原答复后，先实际阅读代码和TeX，再按需使用两个独立检查器。`--reviewed-source`记录源已被审查的前提，不能用旗标代替审查，也不代表安全隔离。

```sh
python scripts/check_trial_code.py --answer qa/trials/assembled-01/answer.json --tasks examples/model-trials/tasks-v2.json --probes examples/model-trials/solver-probes.json --output qa/trials/code-01 --reviewed-source
python scripts/check_trial_latex.py --answer qa/trials/assembled-01/answer.json --output qa/trials/latex-01 --reviewed-source --render --compiler /path/to/xelatex
```

程序检查覆盖指定正成本输入、精确切换点和选用的非整数质量探针，不证明通用求解正确；分数桥接保留分子/分母，不能把检查器的编码错误归于模型。模型代码在不含provider凭据的子进程运行，但此工具不是OS安全沙箱。

公式检查把原始片段直接插入12pt A4夹具，默认2.5cm边距可配置；检查实际编译、缺字和Overfull，并可渲染。外部I/O及动态TeX命令被拒绝；这仍不替代审查。编译成功不等于数学、重叠或整篇版式全部正确。JSON正确、数值正确、代码可运行、公式可编译、人工科学审查分别记录，不合成一个“论文质量满分”。

评测结论写在内部报告；需要公开的维护记录只发布脱敏合成任务与实际结果，清楚区分自动检查、人工审查、代码执行、编译和未验证范围。相同资料只返回正文段落的模型与真正执行完整工具链的代理，其成绩分别说明。边界上的并列最优要明确使用精确数还是浮点容差；参考检查器与求解程序精度口径不一致时，先查接口，不能直接给模型贴错标签。
