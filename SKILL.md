---
name: mathmodel-paper-workflow
description: 依据求解证据迭代定稿中文数学建模竞赛论文，处理摘要与逐问模型、公式图表、物理线稿、PDF/Word排版、原附录保留和支撑材料验收。适用于已有赛题、程序或论文，需要按反馈继续修订并交付可追溯成果的任务。
---

# 数模论文迭代定稿

贯通“题目要求—逐问求解—结果证据—正文表达—图表排版—最终交付”，把用户反馈转为可核验的论文变更。可接续已有建模工作流，不要求安装特定上游技能。

## 接手与确定约束

1. 读取项目 `AGENTS.md`，以及存在时的 `.mathmodel/paper/config.json`。模板、队伍档案和入口文件属于用户数据，不覆盖已有配置。身份信息只进入模板明确要求的非匿名页面。
2. 确定最新**用户指定**文件、可编辑源、输出目录及保留区域。用户改过附录的 PDF 可能比 TeX/Word 更权威，不能用旧源重建这部分。
3. 留存原文件及 SHA-256。在授权目录创建修订源，不覆盖其他方案、历史提交或外部聊天附件。
4. 记录简短约束表：页数口径（含不含摘要/声明/文献）、上限还是精确页数、边距、缩进、图片可见宽度、留白口径、文献要求、附录保留方式、交付格式。最新明确指示覆盖旧值。

**不要固化某篇论文的参数。** 31 页、四边 2.5 cm、首行两字、20% 页尾留白都是一种项目配置，不是竞赛通用标准。只有页数上限时不为凑满页数添加文字；模板与用户要求冲突时说明具体冲突。

## 选择本次需要的步骤

- **多轮反馈、每问公式或检查失败**：读 [修订细则](references/revision-playbook.md)，按需使用反馈记录与逐问证据模板；遇到具体失败查 [恢复手册](references/failure-recovery.md)。简单修改不强制建完整台账。
- **多技能协作或完整复现**：读 [技能协作](references/skill-orchestration.md) 和 [复现手册](references/reproduction-guide.md)。按现有产物选择 MathModelAgent、sci-box、BZD 等阶段技能，不重复部署同名入口；记录安装、阅读与执行的不同状态。需要可运行示例时执行 `python scripts/run_demo.py --output qa/demo`。
- **模型、数值、摘要或措辞**：读 [证据与写作](references/evidence-and-writing.md)。建立每问“输入—假设—方程—算法—输出—验证”对应后写结论。只做排版时不擅自重算或替换模型。
- **图、公式、线稿、分页**：读 [图表与排版](references/figures-and-layout.md)。先修标注和图文顺序，再量化留白；优先编辑矢量源。
- **附录、Word/PDF、支撑包或复现**：读 [编译与交付](references/build-and-delivery.md)。先编译检查正文，最后接回原附录。

## 可重复的检查工具

需要时安装本技能根目录 `requirements.txt` 的依赖。`python` 指当前环境可用的 Python，不写死盘符。

```sh
# 按项目合同检查；合同示例须先替换成该项目的真实路径和约束。
python scripts/audit_contract.py project-contract.json --project-root project --report qa/round-01/layout.json --render-dir qa/round-01/pages

# 只审核正文范围；示例参数按项目替换，页号从 1 开始。
python scripts/pdf_workflow.py audit paper.pdf --last-page 31 --margins-cm 2.5 2.5 2.5 2.5 --blank-limit 20 --report qa/layout.json --render-dir qa/pages

# 对仅含正文部分的 PDF 校验页数上限；确切要求才用 --exact-pages。
python scripts/pdf_workflow.py audit body.pdf --max-pages 31 --report qa/body.json

# 接回原 PDF 第 30 页起的附录；默认完全保留，不改页码。
python scripts/pdf_workflow.py append body.pdf original.pdf final.pdf --appendix-start 30 --report qa/appendix.json

# 已授权补页码且页脚空白时增加：
# --number-pages --footer-height-pt 42 --footer-baseline-from-bottom-pt 25

# 根据白名单打包，生成 SHA-256 清单。
python scripts/package_support.py support-root support-files.json support.zip
```

`audit` 测量版心内整行宽度连续无内容的竖向区间，报告页尾及最大空白带。**不是总白色像素比例，也不能自动证明没有文字重叠。** 它跳过范围外附录，检测疑似未编译公式，输出逐页预览。超标退出码 1，输入错误 2；未提供留白限制时只报告，不发明门槛。

`audit_contract.py` 读取合同的 `audit`、页数、边距与留白字段；其余字段供代理执行，不代表已自动核验。合并 PDF 必须指定正文末页，报告和预览采用新路径；`--dry-run` 仅打印参数。详细字段和命令见 [复现手册](references/reproduction-guide.md#8-让合同直接驱动检查)。

`append` 复核每页原附录的渲染和文字；加页码前检查页脚文字与图形为空，之后验证页脚外一致。已有页码、扫描污点、旋转页或不合适区域会停止，不用白块覆盖。数字签名等 PDF 级元数据不属于视觉保真保证。

## 每轮完成标准

- 变更对应用户反馈；新增分析有数据或推导支持，不以套话填页。
- 数值和结果表可追溯，显示与计算精度分开；不冒充实测或未经运行的验证。
- 编译没有未解决引用、缺字、明显越界；重点页原尺寸查看，正文逐页检查。
- 图例、引线、尺寸线和文字互不遮挡；公式及黑框不裁切；标题后有正文。
- 图表就近放在完整段落之后，同一问的结果不被下一问标题隔开。
- PDF 与被要求的 Word 分别核验；仅检查 PDF 就只报告 PDF 合格。
- 原附录按约定保留，新增页码连续；源、图和支撑包对应同一最终版本。

交付先给最终文件链接，再报告实际页数、留白口径、附录状态及未完成事项，只写已验证内容。用户继续反馈时从最新授权版本修订，不重新解释整套流程。
