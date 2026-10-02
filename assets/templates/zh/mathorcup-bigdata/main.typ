// Original Big Data adaptation. Format baseline: 2025, awaiting 2026 confirmation.
#import "config.typ": *
#set document(title: paper-title, author: ())
#set text(font: ("SimSun", "Noto Serif CJK SC", "FandolSong", "Noto Sans SC"), size: 12pt, lang: "zh")
#set par(justify: true, first-line-indent: 2em, leading: 0.65em)
#set heading(numbering: "1.1")
#set math.equation(numbering: "(1)")
#show heading.where(level: 1): set text(size: 14pt, weight: "bold")
#set page(paper: "a4", margin: 25mm, header: none, footer: none, numbering: none)
#align(center)[
  #table(
    columns: (35mm, 55mm), align: center + horizon, inset: 5pt, stroke: 0.5pt,
    [队伍编号], [#team-number], [赛道], [#track],
  )
  #v(8mm)
  #text(size: 16pt, weight: "bold")[#paper-title]
  #parbreak()
  #text(size: 14pt, weight: "bold")[摘 要]
]
#include "summary.typ"
#parbreak()
#strong[关键词：] #keywords
#metadata("summary end") <bd-summary-end>
#pagebreak()
#outline(title: [目录], depth: 2)
#metadata("contents end") <bd-contents-end>
#pagebreak()
#set page(header: none, numbering: "1", footer: context align(center)[#counter(page).display("1")])
#counter(page).update(1)
#metadata("body start") <bd-body-start>
#include "solution.typ"
#if include-ai-statement {
  heading(level: 1, numbering: none)[AI 工具使用声明]
  include "ai-statement.typ"
}
#include "references.typ"
#metadata("body end") <bd-body-end>
#if include-appendix {
  pagebreak()
  heading(level: 1, numbering: none)[附录]
  [#metadata("appendix start") <bd-appendix-start>]
  include "appendix.typ"
}
#metadata("document end") <bd-document-end>
#let physical-page(mark) = query(mark).first().location().page()
#context [
  #metadata((
    schema_version: 1,
    family: "mathorcup-bigdata",
    contest_year: year,
    format_rules_year: 2025,
    rules_status: "provisional",
    team_number: team-number,
    track: track,
    summary_last_page: physical-page(<bd-summary-end>),
    contents_last_page: physical-page(<bd-contents-end>),
    body_first_page: physical-page(<bd-body-start>),
    body_last_page: physical-page(<bd-body-end>),
    appendix_first_page: if include-appendix { physical-page(<bd-appendix-start>) } else { none },
    total_pages: physical-page(<bd-document-end>),
  )) <bd-boundary>
]
