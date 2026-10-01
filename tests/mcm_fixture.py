"""Small synthetic content for real compiler probes, not a contest solution."""
from pathlib import Path


def fill(folder: Path, engine: str, include_ai: bool = True):
    if engine == "latex":
        (folder/"config.tex").write_text(r"""\newcommand{\MCMYear}{2027}
\newcommand{\TeamControlNumber}{1234567}
\newcommand{\ProblemChosen}{B}
\newcommand{\PaperTitle}{Synthetic Template Fixture}
\MCMIncludeContentstrue
\MCMIncludeAppendixfalse
\MCMIncludeAItrue
""", encoding="utf-8")
        (folder/"summary.tex").write_text(
            "This is a synthetic template fixture, not a competition solution. "
            "It exercises a model, results, a letter and a separate AI report.\n", encoding="utf-8")
        (folder/"solution.tex").write_text(r"""\section{Model}
This synthetic model is included only to exercise mathematical typesetting.
\begin{equation}
\boxed{\frac{dx}{dt}=-kx},\qquad x(0)=1,\quad t\geq0
\end{equation}
\newpage
\section{Results}
The analytic expression for this synthetic example is $x(t)=\exp(-kt)$.
\begin{equation}
x(t)=\begin{cases}1 & t=0\\ \exp(-kt) & t>0\end{cases}
\end{equation}
\newpage
\section{Letter to a Fictional Agency}
This is a synthetic letter fixture. It makes no policy or empirical claim.
""", encoding="utf-8")
        (folder/"references.tex").write_text(r"""\addcontentsline{toc}{section}{References}
\begin{thebibliography}{9}
\bibitem{comap} COMAP. MCM/ICM Rules and Instructions (2027).
\url{https://contest.comap.com/undergraduate/contests/mcm/instructions.html}
\end{thebibliography}
""", encoding="utf-8")
        (folder/"ai-report.tex").write_text(
            "Synthetic AI report fixture for boundary testing only.\n"
            "\\newpage\nAdditional synthetic record.\n", encoding="utf-8")
    else:
        (folder/"config.typ").write_text('''#let year = 2027
#let team-control-number = "1234567"
#let problem-chosen = "B"
#let paper-title = "Synthetic Template Fixture"
#let include-contents = true
#let include-appendix = false
#let include-ai = true
''', encoding="utf-8")
        (folder/"summary.typ").write_text(
            "This is a synthetic template fixture, not a competition solution. "
            "It exercises a model, results, a letter and a separate AI report.\n", encoding="utf-8")
        (folder/"solution.typ").write_text('''= Model
This synthetic model is included only to exercise mathematical typesetting.
$ dif x / dif t = -k x, quad x(0) = 1, quad t >= 0 $
#pagebreak()
= Results
The analytic expression for this synthetic example is $x(t) = exp(-k t)$.
$ x(t) = cases(1 "if" t = 0, exp(-k t) "if" t > 0) $
#pagebreak()
= Letter to a Fictional Agency
This is a synthetic letter fixture. It makes no policy or empirical claim.
''', encoding="utf-8")
        (folder/"references.typ").write_text('''#heading(level: 1, numbering: none)[References]
COMAP. MCM/ICM Rules and Instructions (2027).
#link("https://contest.comap.com/undergraduate/contests/mcm/instructions.html")
''', encoding="utf-8")
        (folder/"ai-report.typ").write_text(
            "Synthetic AI report fixture for boundary testing only.\n"
            "#pagebreak()\nAdditional synthetic record.\n", encoding="utf-8")
    if not include_ai:
        config = folder/("config.tex" if engine == "latex" else "config.typ")
        text = config.read_text(encoding="utf-8")
        text = text.replace(r"\MCMIncludeAItrue", r"\MCMIncludeAIfalse") if engine == "latex" else text.replace("#let include-ai = true", "#let include-ai = false")
        config.write_text(text, encoding="utf-8")
