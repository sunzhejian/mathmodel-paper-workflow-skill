# 工具安装与第一次使用

本页只覆盖此 skill 实际会接触的工具。**运行仓库演示与 PDF 验收只需 Git、Python 和 `requirements.txt`；完成真实赛题时，按选择的模型、论文引擎和图形路线增装。** 软件装好不等于模型已运行，安装记录也不能代替结果验证。下列安装入口链接到各项目官方文档；版本和系统要求随软件更新，以链接中的当前说明为准。

先执行下表的验证命令，复用已有且能运行项目的工具，再安装所选路线的缺项。Codex 已提供可用依赖运行时的环境可直接使用对应解释器；桌面应用、系统 Python 和项目 `.venv` 不一定是同一个环境，安装依赖与运行脚本必须指向同一解释器。只修 PDF 或文字时不用更换用户现有 shell、论文引擎或商业软件路线。

| 用途 | 工具 | 何时需要 | 安装后最小验证 |
| --- | --- | --- | --- |
| 获取仓库、固定上游子模块 | Git | 本地使用本仓库时 | `git --version` |
| 运行检查、打包和合成演示 | Python 3.10+、本仓库依赖 | 本地使用本仓库时 | `python --version`、导入 `pymupdf` |
| 编辑程序和论文源 | VS Code 等文本编辑器 | 想要图形界面时；不是运行依赖 | 打开仓库目录 |
| 数值求解、数据表、数据图 | SciPy、pandas、Matplotlib、openpyxl 等 | 赛题确实采用相应 Python 路线时 | 在项目环境中导入并运行一问脚本 |
| 编译 `.tex` | TeX Live 或 MiKTeX，含 XeLaTeX；需要时配 `latexmk` | 需要本机编译多文件 LaTeX 项目时，二选一 | `xelatex --version`、`latexmk -v` |
| 编译 `.typ` | Typst CLI | 选 Typst 模板时 | `typst --version` |
| 编辑 `.drawio` 和导出线稿 | draw.io Desktop | 需要可编辑示意图时 | 打开图源并导出一张 PDF/PNG |
| 检查 DOCX | Microsoft Word 或 LibreOffice | 交付 Word 时 | 打开、导出 PDF、逐页比较 |
| 特定商业求解、统计或制图 | MATLAB、COMSOL、Stata、Origin/OriginPro | 模型方案明确选用且有许可证时 | 运行一个真实小例子并保存日志 |

## 1. 先把仓库演示跑通

从 [Git 安装页](https://git-scm.com/install/)和 [Python 下载页](https://www.python.org/downloads/)取得适合系统的安装包。Python 的虚拟环境可直接调用其中的解释器，**不必激活环境或修改 PowerShell 执行策略**；[Python 官方 `venv` 文档](https://docs.python.org/3/library/venv.html)也说明了这一路径。

### Windows PowerShell

```powershell
git --version
py -3 --version
$skillBase = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillPath = Join-Path $skillBase 'skills\mathmodel-paper-workflow'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillPath) | Out-Null
git clone --recurse-submodules https://github.com/sunzhejian/mathmodel-paper-workflow-skill.git $skillPath
Set-Location $skillPath
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import pymupdf, numpy, PIL; print('core OK')"
.\.venv\Scripts\python.exe scripts/check_vendor_skills.py
.\.venv\Scripts\python.exe scripts/run_demo.py --output qa/demo
```

`py -3` 不存在时，使用 `python` 或已安装 Python 的完整路径；确认其版本和所在路径后，后续都用**同一个解释器**创建环境、安装依赖和运行脚本。仓库已存在时跳过 `git clone`，进入目录执行 `git submodule update --init --recursive`；演示目录已存在时换用 `qa/demo-2` 等新路径，脚本不会覆盖旧结果。

### macOS / Linux

从同一官方入口安装 Git 与 Python，或使用系统发行版的软件包。示例使用 `python3`；若发行版把 `venv` 拆成单独软件包，先按该发行版说明安装。

```sh
git --version
python3 --version
skill_base="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$skill_base/skills"
git clone --recurse-submodules https://github.com/sunzhejian/mathmodel-paper-workflow-skill.git "$skill_base/skills/mathmodel-paper-workflow"
cd "$skill_base/skills/mathmodel-paper-workflow"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "import pymupdf, numpy, PIL; print('core OK')"
.venv/bin/python scripts/check_vendor_skills.py
.venv/bin/python scripts/run_demo.py --output qa/demo
```

演示完成后查看 `qa/demo/demo-report.json`、`qa/demo/final.pdf` 和 `qa/demo/pages/`；它们来自**合成数据**，不能作为真实赛题的计算结论。[完整产物说明与复现步骤](../references/reproduction-guide.md)列出了每个文件的用途。VS Code 可从[官方安装指南](https://code.visualstudio.com/docs/getstarted/overview)安装，进入仓库后运行 `code .` 打开目录；编辑器不替代 Python、Git 或论文编译器。

## 2. 做真实赛题时增加 Python 数值库

本仓库的 `requirements.txt` 只列 PDF 检查和演示工具的依赖，不强制安装所有建模包。按实际方法在**赛题项目自己的环境**中安装，例如：

```sh
python -m pip install scipy pandas matplotlib openpyxl
python -c "import scipy, pandas, matplotlib, openpyxl; print('model tools OK')"
python -m pip freeze > environment-lock.txt
```

Windows 下把上面的 `python` 换成项目 `.venv\Scripts\python.exe`，macOS/Linux 换成 `.venv/bin/python`。SciPy 用于数值求解，pandas 用于表数据处理，Matplotlib 用于数据图，openpyxl 用于常规 XLSX；是否适用取决于赛题规模和输出要求，超大表格可能需要流式写入。安装和基础用法见 [SciPy](https://scipy.org/install/)、[pandas](https://pandas.pydata.org/docs/getting_started/)、[Matplotlib](https://matplotlib.org/stable/install/index.html) 与 [openpyxl](https://openpyxl.readthedocs.io/en/stable/tutorial.html) 官方文档。每问还需单独运行脚本，核对输入哈希、单位、原精度结果和输出范围；`import` 成功只是环境检查。

## 3. 只安装选中的论文编译路线

**LaTeX：**需要在本机编译多文件 LaTeX 项目时，Windows 可用 [MiKTeX 官方安装指南](https://miktex.org/howto/install-miktex)，跨平台可用 [TeX Live 官方网络安装指南](https://tug.org/texlive/acquire-netinstall.html)。二者选一，安装后重开终端，检查 `xelatex --version` 与 `latexmk -v`；若项目使用 `latexmk`，还要确认它在当前 TeX 环境中可执行。按仓库中实际入口编译，例如：

```sh
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build paper/main.tex
```

`paper/main.tex` 是示例路径；优先遵循项目配置中的入口和工作目录。中文字体、宏包、引用和图路径仍须按编译日志检查。安装 TeX Live 通常比运行本仓库演示占用更多时间与磁盘空间。

**Typst：**从 [Typst 官方开源安装页](https://typst.app/open-source/)选择适合系统的 CLI；其[官方仓库](https://github.com/typst/typst)也列出 Windows `winget install --id Typst.Typst` 和 macOS `brew install typst`。安装后检查 `typst --version`，再按项目入口运行：

```sh
typst compile paper/main.typ deliverables/body.pdf
```

LaTeX 与 Typst 模板不可仅通过改扩展名互换；选定一个引擎后，检查字体、公式、引用与分页。[Typst 官方文档](https://typst.app/docs/)提供语言和编译器说明。

## 4. 图示与 Word 检查

**可编辑示意图：**从 [draw.io Desktop 官方发布页](https://github.com/jgraph/drawio-desktop/releases)安装对应系统版本。打开 `.drawio` 核对文字、箭头、遮挡弧线和图例，再导出 PDF/PNG；命令行可在可执行文件已加入 PATH 时运行，例如：

```sh
drawio -x -f pdf -o figures/roadmap.pdf figures/roadmap.drawio
```

不同系统的命令别名可能是 `drawio`、`draw.io` 或可执行文件完整路径。桌面导出通常需要图形会话；无桌面的服务器优先保留可编辑源，在有桌面的环境导出并目视验图。仓库讲解图的实际命令见[复现手册第 7 节](../references/reproduction-guide.md#7-重绘本仓库的三张讲解图)。

**Word：**有 Microsoft Word 时用它打开最终 DOCX，检查公式、字体、图表、页码并导出 PDF 逐页对照。没有 Word 时可从 [LibreOffice 官方下载页](https://www.libreoffice.org/download/)安装 Writer；[命令行参数文档](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)说明 `--headless` 和 `--convert-to`。先创建 `qa/word-preview` 目录，再把 DOCX 渲染到其中：

```sh
soffice --headless --convert-to pdf --outdir qa/word-preview deliverables/paper.docx
```

Windows 若找不到 `soffice`，使用安装目录中的 `soffice.com` 或直接在 Writer 图形界面导出。**Word 与 LibreOffice 的分页可能不同**；用哪个程序生成最终 DOCX，就优先在那个程序里完成最终视觉核验。

## 5. 商业软件仅在方案确实需要时安装

- **MATLAB：**通过 [MathWorks 官方安装入口](https://www.mathworks.com/help/install/install-products.html)按账号与许可证安装。用于 `.m` 求解脚本时，可先运行 `matlab -batch "disp(version)"` 检查批处理入口，再运行实际脚本并保存输入、版本与日志；`-batch` 的退出码规则见[官方说明](https://www.mathworks.com/help/matlab/ref/matlabwindows.html)。
- **COMSOL：**按[官方安装向导](https://www.comsol.com/support/learning-center/article/comsol-Installation-Companion-58101)选择许可证类型和系统。先用一个小模型验证材料参数、边界、网格与求解器，再与独立数值结果比较；没有实际模型文件和运行记录时不能宣称“COMSOL 验证”。
- **Stata：**只有赛题方案确实采用统计建模且团队有许可证时，按[官方安装指南](https://www.stata.com/install-guide/)选择与许可对应的版本。在 Do-file Editor 中运行并保存 `.do` 脚本、日志及原始/处理后数据；[官方入门手册](https://www.stata.com/manuals/gsw.pdf)说明如何执行 do-file。安装后能打开软件不代表统计结果已复现。
- **Origin/OriginPro：**按[OriginLab 官方安装说明](https://www.originlab.com/index.aspx?go=Support%2FDocumentationAndHelpCenter%2FInstallation%2FDirectInstall)安装并激活。只有选择 Origin 绘图时才考虑 `originpro`；[官方 Python 说明](https://docs.originlab.com/python/)区分内置 Python 和外部 Python。要保存 `.opju` 源、导出图和逐点核验记录；不能以装好软件代替图表结果。

这四项都不是运行本仓库脚本的前置条件。比赛路线若完全由 Python 与选定排版引擎完成，不必额外安装它们。

## 6. 常见定位

| 现象 | 先检查 |
| --- | --- |
| `python`/`pip` 指向不同位置，或导入包失败 | 在创建环境、安装和运行三个步骤中使用同一个 `.venv` 解释器；先输出版本和解释器路径 |
| `vendor/` 只有空目录 | 在仓库根目录执行 `git submodule update --init --recursive`，再运行 `scripts/check_vendor_skills.py` |
| `xelatex`、`latexmk`、`typst` 找不到 | 是否实际选择并安装了该引擎；重开终端检查 PATH，必要时用完整路径 |
| 图能打开但命令行导出失败 | 核对 draw.io 桌面版安装路径、CLI 名称与图形会话；先从 GUI 导出一张 |
| DOCX 与 PDF 页数或图位不同 | 用交付目标的 Word/Writer 逐页渲染和修版，不用 PDF 检查结果推断 Word 合格 |
| MATLAB、COMSOL、Stata、Origin 启动或许可失败 | 先按各厂商账号/许可证说明处理，不换用虚构验证记录 |

环境验证只回答“工具能否启动”；论文交付仍需按[证据链](../references/evidence-and-writing.md)、[逐页验收](../references/build-and-delivery.md)和[支撑包复现](../references/reproduction-guide.md)分别检查。

## 7. 可选：用模型套餐测试本 skill

这是开发与行为评测用途，不是求解赛题的必装依赖。只有使用者明确要求调用模型时才启用。可用已安装的 Codex CLI；安装入口和基础用法见[官方文档](https://developers.openai.com/codex/cli/reference)。先检查 `codex --version` 与 `codex exec --help`，本仓库单次试用器的实际验证版本为0.144.1，需要 `--ignore-user-config`、`--ephemeral` 和配置覆盖等选项。

先按[真实模型行为评测](../references/model-trials.md)准备匿名任务，再将套餐支持的公开地址、模型名称和密钥环境变量名称写入路线配置。**配置文件不写密钥**，通过本机私有方式在父进程加载；不使用打印环境变量的命令来证明配置成功。千问 Token Plan、火山 Agent Plan、火山 Coding Plan 的地址分开使用，示例位于 [providers.json](../examples/model-trials/providers.json)。套餐和模型变化时以厂商当前官方文档为准，不能从名称或密钥前缀推断全部权限。

`run_codex_trial.py` 每次仅执行指定路线并保存脱敏结果；不会修改全局模型配置，不直接充当API服务，鉴权失败不会换用按量付费地址。当前测试要求模型返回匿名解题片段，再由维护者核对、执行和编译；这与让模型自主跑完实际论文项目是不同的测试范围。
