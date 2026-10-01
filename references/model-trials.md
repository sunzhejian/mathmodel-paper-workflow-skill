# 用真实模型产物改进 skill

只在使用者要求多模型试用、行为评测或维护本 skill 时读取。普通论文任务不自动增加评测、模型调用或费用；研发只使用匿名合成材料，不改写既有论文。

## 有限的一轮改进

1. 先确定实际可用的工具、套餐端点、模型名称、材料授权和调用次数。本轮可以采用“基线两题 → 查实失败 → 局部修订 → 新数据复测”，不是无限自改或后台定时任务。套餐名称不等于模型名称；最新官方文档与实际鉴权共同决定可用路线。失败的鉴权不计作模型能力差。
2. 冻结匿名题目、选用的 skill 文本、输入数据和验收依据。不同路线获得相同任务和相同资料，不把参考答案、其他路线结果或评审意见混入基线提示词。记录模型调用名、编程工具版本、推理选项、时间、用量和原始产物。结果文件用新目录，保留输入和输出哈希。
3. 要求交付实际解题产物：模型、计算结果、必要程序、Summary 和题面指定材料。不要用“请评价本 skill”或模型自称已经运行、已经正确作为效果证据。无工具任务和实际工具执行分别记录，不能互称。
4. 先用可信计算核对数值与约束，再逐段核对科学含义、摘要和 memo/letter。检查器只认可它实际检测的项目；代码存在不等于代码运行，LaTeX 字符串存在不等于公式已编译。外部生成的程序和 TeX 先审查，再在不含密钥的隔离目录运行或编译。
5. 根据查实错误做局部修订。例如漏掉切换点上的并列最优方案、把识别集合叫成置信区间、Summary 的建议与情景结果冲突。修订应改善相应决策，不堆通用禁令，不给所有问题强加该案例的模型、单位、题数或输出格式。
6. 保留基线输入，用独立的新参数或任务复测；如果要判断更新效果，再以同一旧任务做对照重跑。新任务和旧任务难度不同，不能直接把得分差归因于 skill 更新。记录未修复项、失败与未执行项，不把小任务表现外推成完整论文水平或获奖概率。

## 密钥与调用材料

凭据只在本机私有文件或进程环境中读取，不进入提示词、源码、CLI 参数、终端输出、公开报告或 Git。截图凭据只做本地识别，字符无法确认时请求使用者在本机更新文件，不能批量猜测密钥。模型生成的代码在不含凭据的环境执行。

按套餐允许的编程工具方式接入；不要把交互套餐改造成自建批量后端，也不要在套餐鉴权失败后自动切到按量付费端点。网络错误和缺少权限单列，保留可用路线继续独立测试。失败重试需有上限和理由，不能凭重试次数制造能力结论。

## 仓库提供的离线夹具

原创建模小题位于 [examples/model-trials/tasks.json](../examples/model-trials/tasks.json)。基线含混合运输成本切换与潜在投票推断；新数据版本包含三方案同时最优和不同的识别边界。这不是 COMAP 官方题目，也不是正式论文。源码 [scripts/model_trial.py](../scripts/model_trial.py) 不联网、不读取密钥、不执行模型代码。

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

评测结论写在内部报告；需要公开的维护记录只发布脱敏合成任务与实际结果，清楚区分自动检查、人工审查、代码执行、编译和未验证范围。相同资料只返回正文段落的模型与真正执行完整工具链的代理，其成绩分别说明。边界上的并列最优要明确使用精确数还是浮点容差；参考检查器与求解程序精度口径不一致时，先查接口，不能直接给模型贴错标签。
