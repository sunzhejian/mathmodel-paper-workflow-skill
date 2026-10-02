"""Synthetic typesetting fixture only: no competition data or empirical claims."""
from pathlib import Path
import os


def font_dir(folder: Path) -> Path | None:
    # A real pinned font, supplied explicitly; do not pretend PDF font buffers
    # are accepted by every typesetter.
    value = os.environ.get("MATHMODEL_CJK_FONT_DIR")
    return Path(value).resolve(strict=True) if value else None


def fill(folder: Path, engine: str, appendix: bool = True, ai: bool = False):
    suffix = "tex" if engine == "latex" else "typ"
    if engine == "latex":
        config = r"""\newcommand{\BigDataYear}{2026}
\newcommand{\BigDataTeamNumber}{MCB2600001}
\newcommand{\BigDataTrack}{A}
\newcommand{\BigDataPaperTitle}{合成排版测试：模型与数据分析}
\newcommand{\BigDataKeywords}{合成测试；常微分方程}
\BigDataAppendixtrue
\BigDataAIStatementfalse
""".replace(r"\BigDataAppendixtrue", r"\BigDataAppendixtrue" if appendix else r"\BigDataAppendixfalse")
        config = config.replace(r"\BigDataAIStatementfalse", r"\BigDataAIStatementtrue" if ai else r"\BigDataAIStatementfalse")
        summary = "本文件使用匿名合成内容检验模板的首页、目录、公式和页码。模型采用常微分方程及其解析表达式，结果不作为竞赛解答。\n"
        solution = r"""\section{数据与模型}
本节为合成排版内容。设 $x(0)=1$，参数 $k>0$，考虑
\begin{equation}\boxed{\frac{dx}{dt}=-kx},\qquad t\geq 0\end{equation}
其解析表达式为 $x(t)=\exp(-kt)$。
\subsection{符号说明}
\begin{center}\begin{tabular}{lll}\toprule 符号&含义&单位\\\midrule
$t$&时间&$\mathrm{s}$\\$k$&系数&$\mathrm{s}^{-1}$\\$x$&无量纲状态&1\\\bottomrule\end{tabular}\end{center}
\newpage
\section{检验与结果}
对上述解析表达式求导，所得导数满足所设微分方程。本节只检验合成内容的数学排版。
"""
        refs = r"""\begin{thebibliography}{9}
\addcontentsline{toc}{section}{参考文献}
\bibitem{rules} MathorCup数学应用挑战赛组委会. 大数据竞赛论文格式及提交规范. 2025.
\end{thebibliography}
"""
        extra = "合成程序说明与源代码页。\n\\begin{verbatim}\nfrom math import exp\n\ndef state(t, k):\n    return exp(-k * t)\n\\end{verbatim}\n"
    else:
        config = '''#let year = 2026
#let team-number = "MCB2600001"
#let track = "A"
#let paper-title = "合成排版测试：模型与数据分析"
#let keywords = "合成测试；常微分方程"
#let include-appendix = true
#let include-ai-statement = false
'''.replace("include-appendix = true", "include-appendix = " + str(appendix).lower())
        config = config.replace("include-ai-statement = false", "include-ai-statement = " + str(ai).lower())
        summary = "本文件使用匿名合成内容检验模板的首页、目录、公式和页码。模型采用常微分方程及其解析表达式，结果不作为竞赛解答。\n"
        solution = '''= 数据与模型
本节为合成排版内容。设 $x(0)=1$，参数 $k>0$，考虑
$ (dif x) / (dif t) = -k x, quad t >= 0 $
其解析表达式为 $x(t) = exp(-k t)$。
== 符号说明
#table(columns: 3, [符号], [含义], [单位], [$t$], [时间], [s], [$k$], [系数], [s⁻¹], [$x$], [无量纲状态], [1])
#pagebreak()
= 检验与结果
对上述解析表达式求导，所得导数满足所设微分方程。本节只检验合成内容的数学排版。
'''
        refs = r'''#heading(level: 1, numbering: none)[参考文献]
\[1\] MathorCup数学应用挑战赛组委会. 大数据竞赛论文格式及提交规范. 2025.
'''
        extra = "合成程序说明与源代码页。\n```python\nfrom math import exp\n\ndef state(t, k):\n    return exp(-k * t)\n```\n"
    for name, content in [("config", config), ("summary", summary), ("solution", solution),
                          ("references", refs), ("appendix", extra), ("ai-statement", "合成披露段落，仅用于检验可选位置。\n")]:
        (folder / (name + "." + suffix)).write_text(content, encoding="utf-8")
