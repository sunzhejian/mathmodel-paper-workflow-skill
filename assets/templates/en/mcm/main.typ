// Original MCM/ICM project adaptation. No external Typst packages are required.
#import "config.typ": *
#set document(title: paper-title, author: ())
#set text(size: 12pt, lang: "en")
#set par(justify: true, first-line-indent: 0pt, spacing: 0.45em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): set text(size: 14pt)
#set page(
  paper: "a4",
  margin: 1in,
  footer: none,
  header: context [
    Team \# #team-control-number
    #h(1fr)
    Page #counter(page).get().first() of #counter(page).final().first()
    #line(length: 100%, stroke: 0.4pt)
  ],
)
#table(
  columns: (1fr, 1.25fr, 1.25fr),
  inset: (x: 2pt, y: 3pt),
  stroke: none,
  align: center,
  [*Problem Chosen*], [*#year MCM/ICM* #linebreak() *Summary Sheet*], [*Team Control Number*],
  [*#problem-chosen*], [], [*#team-control-number*],
)
#line(length: 100%, stroke: 0.7pt)
#align(center)[#text(size: 14pt, weight: "bold")[#paper-title]]
#heading(level: 1, numbering: none, outlined: false)[Summary]
#include "summary.typ"
#metadata("summary end") <mcm-summary-end>
#pagebreak()
#if include-contents {
  outline(title: [Contents], depth: 2)
  pagebreak()
}
#include "solution.typ"
#include "references.typ"
#if include-appendix { include "appendix.typ" }
#metadata("solution end") <mcm-solution-end>
#if include-ai {
  pagebreak()
  heading(level: 1, numbering: none, outlined: false)[Report on Use of AI Tools]
  [#metadata("AI start") <mcm-ai-start>]
  include "ai-report.typ"
}
#let page-of(mark) = {
  let matches = query(mark)
  if matches.len() == 0 { 0 } else { matches.first().location().page() }
}
#context [
  #metadata((
    schema_version: 1,
    family: "mcm-icm",
    contest_year: year,
    team_control_number: team-control-number,
    problem: problem-chosen,
    summary_last_page: page-of(<mcm-summary-end>),
    solution_last_page: page-of(<mcm-solution-end>),
    ai_first_page: if include-ai { page-of(<mcm-ai-start>) } else { none },
    total_pages: counter(page).final().first(),
  )) <mcm-boundary>
]
