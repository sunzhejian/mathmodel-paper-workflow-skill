# 可选的完整项目模型试用

此入口服务于 skill 研发中的独立模型试用。普通使用者仍通过已有 IDE/代理工具运行任务，不需要配置 MCP、模型账户或审批 JSON。完整原题和数据由使用者提供；独立版本不读取旧论文、参考答案或其他模型的科学解法。

[`workflow_project_server.py`](../scripts/workflow_project_server.py) 在一个独立工作区提供冻结材料读取、模型产物写入、代码提交审阅、固定解释器执行以及已有排版工具。宿主选择不可变输入目录、实际 Python/Typst/字体路径和工作区外的审批记录：

```json
{
  "name": "workflow_project",
  "command": [
    "/path/to/python", "-X", "utf8",
    "/path/to/mathmodel-paper-workflow/scripts/workflow_project_server.py",
    "--workspace", "/path/to/research/model-project",
    "--inputs", "/path/to/research/original-inputs",
    "--python", "/path/to/solver-python",
    "--compiler", "/path/to/typst",
    "--approvals", "/path/to/research/host-reviews/approvals.json",
    "--font-dir", "/path/to/fonts"
  ]
}
```

路径替换为宿主真实路径，配置不含凭据；如需实际 draw.io 导出再提供 `--drawio`。通过当前 `tools/list` 发现全部工具，不模仿工具名称输出调用标签。材料和排版工具沿用其已有合同，这里新增：

| 工具 | 实际行为 |
| --- | --- |
| `list_inputs` / `read_input_file` | 分页读取冻结的原件清单与 UTF-8 原文/转写；二进制原件需对应阅读器 |
| `write_artifact` | 写入自身 `code/results/figures/paper/reports` 等允许的文本位置；保存修改前后文本快照，不能改原始材料或既有验收 PDF |
| `request_solver_execution` | 提交入口 SHA、完整 `code/**/*.py` 清单与树哈希；不执行程序、不替宿主批准 |
| `run_approved_solver` | 仅执行宿主审阅批准的同一入口和整个代码树，使用固定 Python、固定工作目录与清洁环境 |

宿主先实际阅读所有 Python 源，核对读写位置、外部调用、依赖和科学任务范围。审批只表示允许运行这份源，不表示方法正确。记录示例：

```json
{
  "schema_version": 1,
  "approvals": [{
    "path": "code/01_solve.py",
    "sha256": "REPLACE_WITH_REVIEWED_ENTRY_SHA256",
    "code_tree_hash": "REPLACE_WITH_REVIEWED_COMPLETE_PYTHON_TREE_HASH",
    "approved": true
  }]
}
```

审批文件位于模型写入范围、输入及 skill 分发目录之外。辅助模块变更也需要新审阅/哈希；批准后使用该代码树快照，不从变化后的活动源悄悄运行。执行没有任意 shell 或模型自定参数，子进程不继承 provider 密钥，180秒超时；较长工作按任务拆分或使用另行验证的运行器，不能把超时残留当作完成。它**不是操作系统沙箱**，不能通过哈希和清洁环境宣称任意不可信代码安全。

服务重启仍校验初始冻结输入。执行前后核对输入、源树与验收 PDF，保留输出哈希、标准输出/错误及执行状态；保护日志和产物历史不能被模型覆盖。`results/figures/reports` 的执行前后文件另存内容快照，按SHA复用，并记录新增、修改、沿用及删除；沿用旧文件不冒充本轮生成。默认预算为128MiB/文件、512MiB/轮及每阶段4096文件，完整保存失败不静默截断：执行前异常拒绝启动，执行后异常标为历史不完整及未通过。需要更大产物的任务使用明确适配的其他运行器，不以提高测试成绩为由跳过原件保护。

非零退出、输入改变或未批准程序不算执行通过；退出0只说明列明程序运行，`scientific_correctness_verified` 仍为 false。模型改数据解析、科学方程或论文内容，由模型自己提交新版本，宿主不能悄悄补写后记作其独立成绩。

`compile_paper` 编译前检查完整数学关系，编译后再检查真实 PDF 的疑似单变量编号/残留运算符。严重碎裂时拒绝更新验收 PDF；待复核提示明确查看，编译成功不证明推导正确。最终宿主按最初确定的赛制、摘要分页、字号、页数口径和逐问产物独立验收，不能只相信模型可编辑的 `rendering-contract.json` 或让其降低最低页数而算完成。

客户端完整返回、材料读取、代码允许执行、程序运行、数据/科学检验、论文及全部材料验收分别报告。当前实题阶段记录见[2026-10-03试验](../docs/northeast-trials-20261003.md)；接口实现或单元测试通过不补记为独立长论文完成。
