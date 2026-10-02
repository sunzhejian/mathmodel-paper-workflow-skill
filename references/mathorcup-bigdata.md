# MathorCup 大数据竞赛：2026 预备适配

适用于秋季 MathorCup 大数据竞赛，不与春季 MathorCup 数学应用挑战赛的模板合并。模板 id 为 `mathorcup-bigdata-latex` / `mathorcup-bigdata`，分别使用 LaTeX / Typst。用户明确说“十月、妈妈杯、大数据”时，优先识别这一赛项；尚不清楚赛项时只补问普通 MathorCup 还是大数据赛、比赛年份与阶段。既有论文和项目配置保持权威，新模板只创建在新目录。

## 规则来源与版本状态

核对日期：2026-10-02（北京时间）。已读取[2026 第七届报名通知与所附章程](https://mathorcup.org/detail/2494)，下载核对官方 PDF；另读取[2025 大数据赛论文格式及模板公告](https://www.saikr.com/c/nd/34739)及其原 Word 样表。此次检索尚未获得独立的 **2026 大数据赛论文格式及提交规范和专用模板**，因此本项目提供的是原创预备适配，`rules_status=provisional`，论文格式基线为 2025；不能称为“2026 官方模板”或直接判为今年可提交。

| 信息 | 已确认的来源与用途 |
| --- | --- |
| 初赛 2026-10-23 18:00 至 10-30 20:00，复赛 12-04 18:00 至 12-11 20:00 | 2026 通知；时间均为北京时间，比赛阶段分别记录 |
| 论文、结果数据集、计算程序源代码及运行说明 | 2026 通知与章程；具体输出按选定题面确定 |
| 论文名为题号＋参赛编号，承诺书再加“承诺书”，支撑包再加“附件” | 2026 通知第 9 条及 PDF 第 3 页；队号示例以 MCB26 开头，别用春季 MC 或国赛编号 |
| 首页包含论文题目、摘要、关键词；第二页目录；其后正文从 1 编页码，页脚居中 | 2025 格式基线；目录和页码由编译生成 |
| 首页队伍编号和赛道表格 | 2025 官方 Word 样表；保留匿名比赛编号，姓名、学校与签名不进入论文 |
| 无页眉，中文论文，正文 30 页以内，附录不限页数 | 2025 格式基线；2026 格式公布后必须重新核对，不套用国赛 31 页或美赛 25 页 |
| 字体、字号、行距、边距等未统一要求 | 2025 格式基线；模板采用 A4、12pt、四边 2.5cm 是可调整的版式选择 |
| AI 材料位置及具体要求 | 当前尚未核验独立的 2026 规定；记录真实使用情况，取得适用规则后处理，不自动照搬国赛或美赛位置 |

官方文件仅留在本地审查目录，仓库不复制承诺书、签名/印章或原 Word 文件。公开适配源自行实现结构，并提供官方获取入口。下载核验记录：2026 通知 PDF SHA-256 `a45b950e7284ede52ea3dd1ceb11da83982fa34eebbd23147fc69676eec3a9f0`；2025 格式 PDF `66e392589916e29d4695db44fe3943b947ff050e82fc1659241307ec6b3ce868`；2025 Word 样表 `609bc4f5e59479a3d228e00e7fa703ce0486dc9cd0a55b5fabd5fd5b5beb5061`。

## 选择与初始化

先沿用用户已选大方向，再确定实际题目、阶段和排版引擎。盘点时能看到规则年份和预备状态；已有普通 MathorCup 配置不能当作用户已经确认了大数据模板。

```sh
python -X utf8 scripts/template_inventory.py --project-root 项目目录 --category paper --family mathorcup-bigdata
python -X utf8 scripts/prepare_mathorcup_bigdata_template.py --engine latex --output 新项目目录/paper-bigdata
# 或 --engine typst；目标目录必须尚不存在。
```

修改新目录的 `config.tex` / `config.typ`：填写论文标题、实际 MCB 编号、A/B 赛道、关键词和年份。按题面在 `solution` 中覆盖全部子问，不固定三个问题，也不凭模板章节增加模型。`summary`、`references`、`appendix` 均有明确待替换标记，骨架能编译不代表已经成稿。

默认保留附录入口，供实际使用的软件、命令和全部程序；源文件及操作说明仍按要求单独交付。受保护的旧 PDF 附录沿用原来的保真拼接流程，不能拿模板空附录覆盖它。`include-ai-statement` / `BigDataAIStatement` 只是可选正文插入位置，默认关闭不代表未使用 AI；是否开启及放置位置由当前规定与真实记录决定。

## 编译与核对

LaTeX 使用 XeLaTeX 与 ctex/Fandol 中文字体，避免原上游模板固定 macOS 字体的问题。在论文目录创建 `build`，连续编译至引用与目录稳定：

```sh
xelatex -interaction=nonstopmode -halt-on-error -no-shell-escape -output-directory=build main.tex
# 通常至少两遍；MiKTeX 测试使用 --disable-installer，不自动安装包。
```

Typst 不依赖在线包。中文需要可用字体，可在 `main.typ` 的字体选项中选择已安装的宋体/Noto Serif CJK/Noto Sans SC，或用 `--font-path` 指向有许可的本地字体目录。不能以编译成功代替缺字与中文形态检查。可选的便携测试字体取得命令为：

```sh
# 从 skill 根目录取得字体；命令打印绝对 font_dir。
python -X utf8 scripts/fetch_cjk_test_font.py --output qa/cjk-fonts
```

字体与 OFL 许可证来自 [Google Fonts 的固定提交](https://github.com/google/fonts/tree/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/notosanssc)，下载前后按本项目记录的 SHA-256 校验，保存到显式目录，不安装到系统、不覆盖不同哈希的既有字体。仓库不分发字体二进制。CI 用该字体运行中文编译，并关闭系统字体搜索；本地回归可设置 `MATHMODEL_CJK_FONT_DIR` 指向同一目录。没有显式字体目录时，该项便携中文编译测试标记跳过。

```sh
# 在新论文目录执行；将 FONT_DIR 换成上面打印的绝对字体目录。
typst compile --font-path FONT_DIR main.typ build/main.pdf
typst query --font-path FONT_DIR main.typ '<bd-boundary>' --field value --one > build/main.bigdata.json
```

Windows PowerShell 将 `query` 标准输出写入文件时用 UTF-8（例如管道到 `Set-Content -Encoding utf8`），避免旧版默认编码；编译与查询须使用同一源、同一字体路径。LaTeX 自动导出相同语义的 `main.bigdata.json`，记录物理页边界，正文打印页码重新从 1 开始。

```sh
python -X utf8 scripts/check_mathorcup_bigdata_pdf.py paper-bigdata/build/main.pdf --metadata paper-bigdata/build/main.bigdata.json --year 2026 --report qa/bigdata-round-01.json
```

检查包括摘要/目录边界、正文页数、附录起点、首页匿名编号与赛道、无文字页眉、页脚编号及未填标记。报告保留 `format_rules_year=2025`、`rules_status=provisional` 和 `current_format_confirmation_required=true`；退出 0 只表示覆盖的格式检查通过。它不证明全篇匿名性、图像页眉、实际结果、引文、AI 披露和所有材料合格。元数据、报告和当前 PDF 须同版；源更新后重新编译并用新报告路径检查。

之后沿用已有图文视觉、留白、公式、引用、原附录保真及交付清单检查。不要把国赛匿名首页的“去队号抬头”检查套到这个样表；大数据编号按实际官方模板处理。

需要复查适配本身时，可运行合成排版预览（有相应编译器才执行）：

```sh
python -X utf8 scripts/preview_mathorcup_bigdata.py --engine typst --output qa/bigdata-preview-01
# 也可选择 latex，或用 --compiler 指定已有可执行文件。
```

脚本在新目录生成匿名合成源码、编译 PDF、边界 JSON、格式报告和逐页 PNG，不读取正式赛题或用户论文。可用 `--font-path qa/cjk-fonts` 或上述环境变量指定便携字体，此时禁用系统字体来检查可迁移性。合成夹具刻意分页以检查边界，不能当作推荐内容密度或完整竞赛论文。

## 材料出口与后续更新

按 2026 通知及题面分别核对：论文 PDF、结果数据、完整源代码/运行说明、官方承诺书及题目要求的支撑材料。结果文件的字段、行序、单位和命名从当题要求读取，不能写死分类、预测任务或某种评分。承诺书使用对应年度原表，由队员核对真实信息并实际签名；模型代码和复现材料不能代替签署。

发布 2026 格式后：核对比赛名称、年份与初/复赛适用范围，逐项比较首页、目录、匿名性、页数、附录、代码、AI 材料和命名；按证据更新本项目适配源、profile、规则年份及检查器，并跑两引擎编译和反例测试。未完成该核对前保留预备状态。用户要求后续监测时再建立或更新对应任务，不因制作模板自行增加定期通知。
