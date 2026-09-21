# 详细复现手册

本仓库能直接复现 PDF 检查、原附录拼接与核验、白名单打包和讲解图源。**真实模型仍需对应题面、数据、方程、求解代码及环境**；示例不会生成或冒充原竞赛论文的计算结论。

## 1. 干净环境运行

建议 Python 3.11；支持的底线见 README。以下命令都从仓库根目录执行。若已经安装为 skill，直接进入该目录，不必重复克隆。

```sh
git clone https://github.com/sunzhejian/mathmodel-paper-workflow-skill.git
cd mathmodel-paper-workflow-skill
python -m venv .venv
```

Windows PowerShell 不必更改执行策略，直接使用环境内解释器：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/run_demo.py --output qa/demo
.\.venv\Scripts\python.exe -m pip freeze > qa/demo/environment-lock.txt
```

macOS/Linux：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_demo.py --output qa/demo
.venv/bin/python -m pip freeze > qa/demo/environment-lock.txt
```

后续文中的 `python` 均替换为所选环境的解释器。示例目录必须不存在，重复运行请用 `qa/demo-2`；脚本不会覆盖上次交付。依赖给出兼容范围，复现某次具体运行时同时保存仓库提交号、`pip freeze` 和工具版本。PDF 元数据及 ZIP 时间戳可能不同，不要求跨环境文件字节相同。

## 2. 一条命令演示了什么

`run_demo.py` 完成以下真实操作，不需要 Office、LaTeX、Origin 或私人附件：

1. 写出一份独立的合成解析计算脚本：`y(t)=exp(-0.2t)`，时间为整数 0 至 20。输出全精度 CSV；这不是药材模型或实验数据。
2. 运行该脚本，核对首值、末值及单调性。
3. 用这些数据制作两页英文 PDF 测试样稿，避免依赖中文字体。它只是自动检查的夹具，不作为中文论文模板。
4. 制作一页“原正文”加两页“原附录”的合成 PDF，保存原文件哈希。
5. 检查两页正文的留白和原始公式文本，输出 JSON 与页图。
6. 单独构造大留白与未编译公式两个反例，确认工具能拒绝，而不是只演示成功路径。
7. 把两页原附录拼到新正文后，补页码 3、4；逐页比较页脚外渲染和文字，并确认原文件未变。
8. 按白名单打包脚本与结果，回读哈希清单。汇总 `demo-report.json`。

预期产物：

```text
qa/demo/
  support/code/problem1.py       # 可独立重跑的合成计算
  support/results/series.csv     # 21 行数据，不含表头
  body.pdf                      # 2 页自动检查夹具
  original.pdf                  # 1 页旧正文 + 2 页受保护附录
  final.pdf                     # 2 页新正文 + 2 页原附录
  bad-whitespace.pdf / bad-formula.pdf
  layout.json / appendix.json / bad-whitespace.json / bad-formula.json
  pages/                        # 正文页图与缩略拼图
  support-files.json / support.zip
  demo-report.json               # passed=true、预期失败原因、总页数4
```

自动检查通过后仍应打开 `pages/contact_001.png` 与 `final.pdf`。只凭退出码不能判断文字遮挡、物理箭头或论文论证正确。

## 3. 复用真实项目的目录与证据接口

```text
project/
  AGENTS.md
  .mathmodel/paper/config.json   # 用户数据，不提交到公开示例仓库
  input/                        # 原题、原始附件、用户改过的原附录
  code/problem1.py ...           # 每问入口，允许共用有说明的 core.py
  results/                      # 原精度数值、参数、单位、运行信息
  figures/                      # 数据图及线稿的源和导出
  paper/main.tex                # 或已有 Typst / Word 入口
  reports/                      # 证据表、审查、编译、视觉检查记录
  deliverables/                  # 最终文件和支撑包
```

每问至少记录以下证据行，不把“计划验证”填为“已通过”：

| 任务 | 输入与假设 | 方法与变量范围 | 运行命令 | 输出证据 | 检验与边界 |
| --- | --- | --- | --- | --- | --- |
| Q1 示例 | 合成参数 k=0.2，t≥0 | 解析指数函数 | `python code/problem1.py` | series.csv，21 行 | 首末值及单调性；不代表实测验证 |

真实项目还要记录随机种子（如适用）、软件版本、数据哈希、收敛参数与输出精度。阈值判断用未舍入值；四位小数只控制展示。模型参数变化须重算相关结果，不只改摘要数值。

## 4. 复现历史技能配置

安装路线与作用见 [技能协作](skill-orchestration.md)。需要复现上游时从锁定文件获取地址与提交，逐个执行，例如：

```sh
git clone https://github.com/jihe520/MathModelAgent vendor/MathModelAgent
git -C vendor/MathModelAgent checkout 83d8783187a2d29dda1b046cb667009cc50c8203
git clone https://github.com/jihe520/sci-box vendor/sci-box
git -C vendor/sci-box checkout 9687d2a52037e92bf68a781b9b1e061ca03c8125
git clone https://github.com/BZDmathclub/bzd-math-modeling-skills vendor/BZD
git -C vendor/BZD checkout 332d55c2f3244c9e193e90749f42bcc0d534ce53
git clone https://github.com/hang-jin/editaplot vendor/EditaPlot
git -C vendor/EditaPlot checkout 01721038afd212103d96225319b22d1bbfe32270
```

从各仓库查找 `SKILL.md`，读取它的安装说明，按 `name` 去重后安装所需技能。不要递归复制所有文件夹到技能目录，也不要把 `vendor` 提交为本仓库原创内容。`mma-paper` 没有已核验公开来源，需要使用项目现有副本；缺少它不妨碍运行本仓库的演示与验收工具。

## 5. 实际论文的编译与迭代

1. 把最新指令落实到 [约束合同示例](../examples/workflow-contract.json)。本示例用于人工/代理读取，CLI 不会自动解析它；调用命令的参数必须与合同一致。
2. 找到可编辑源。用户指定的 PDF 与旧 TeX 不同，应先比对正文和保留区域，不能覆盖用户手改附录。
3. 按每问组织模型：输入、假设、方程/方程组、参数与单位、变量范围、求解结果、含义。共享理论放前面，每问保留自己的关键公式。方程后有范围时用逗号分隔；没有续接内容时按用户/模板约定统一标点。
4. 适度加粗关键方法与结果；框选最终模型、判据或主要结果，不把全部公式加框。摘要仅使用已核验数值。符号表一行一个符号。
5. 文献逐条核对作者、题名、年份与出处；用户要求“知网可查”时需要检索证据，不能仅凭中文题名判断。按要求在相关正文位置用中括号上角标。
6. 使用原项目编译器。下面只是一种 XeLaTeX 路线，不替换原来的构建配置：

```sh
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build paper/main.tex
```

若项目用相对资源路径，按原构建脚本指定的工作目录执行。检查日志中的缺字、未定义引用与越界；编译成功并不等于排版完成。

7. 对正文部分执行 `audit`，查看所有正文页及重点放大图。先调整浮动体、图表就近顺序、图内外白边及段落完整性，再微调图尺寸。图片按**可见主体**对齐版心，图框空边不等于有效内容。不要靠拉大行距、插空行或无依据分析凑页数。
8. 留白超过阈值时，返回源文件修订并重编译；没有超过就不继续为了数字挤压可读性。算法测的是整行宽的连续空白带，不是所有空白像素面积；图内部两列之间的白区不由该指标约束。
9. Word 若在交付范围，单独检查其公式对象、字体、分页与图片，不把 PDF 合格推断成 DOCX 合格。
10. 最后才运行 `append`，接回原附录。页号参数是物理 PDF 页，不是印刷页脚；已有页码不要覆盖。留存附录比对报告，再打包。

## 6. 支撑材料与发布

支撑包使用逐文件白名单，包含独立求解入口、必要公共模块、依赖说明、处理后题目附件数据、结果表、必要复验记录和按规则要求的 AI 使用说明。原赛题 PDF 不默认入包；“处理后的附件”与“赛题题面”应分开。匿名要求同时适用于文件名、代码注释和元数据。

先逐条审查白名单，再执行 `package_support.py`。它防止路径逃逸并校验哈希，但不会理解文档中是否有身份信息。公开技能仓库不等于竞赛支撑包，不能把私人项目文件混进公开仓库。

## 7. 重绘本仓库的三张讲解图

```sh
python scripts/generate_diagrams.py --output docs/figures
drawio -x -f png -s 1.5 -b 0 -o docs/figures/01-skill-map.png docs/figures/01-skill-map.drawio
drawio -x -f png -s 1.5 -b 0 -o docs/figures/02-evidence-chain.png docs/figures/02-evidence-chain.drawio
drawio -x -f png -s 1.5 -b 0 -o docs/figures/03-layout-loop.png docs/figures/03-layout-loop.drawio
```

需要已安装 draw.io 桌面版，命令别名随系统安装而不同；服务器需图形会话或相应虚拟显示。中文字体使用 Microsoft YaHei，其他系统建议安装 Noto Sans CJK SC 并在源图中替换字体。PNG 因字体与 draw.io 版本可能略有不同，XML 几何定义可重复生成。

若装有 scibox-diagram，对每张源图运行其 `scripts/check_layout.py <图.drawio> --strict`，再用 `scripts/export_figure.py <图.drawio>` 导出。图源生成不依赖该技能，版式检查与导出借助其已安装工具；本仓库不复制上游实现。导出后进行两轮视觉复核：第一轮检查文字、重叠与裁切，第二轮检查箭头逻辑、节点顺序与对齐。
