"""Locate workflow leakage and optional editorial candidates without rewriting sources."""
from __future__ import annotations

import argparse
from bisect import bisect_right
import fnmatch
import json
from pathlib import Path
import re
import sys


# Editing instructions addressed to an assistant, not style scores.
# Generic terms such as 用户指定, 试运行, 显著 and 不能 are deliberately absent.
LEAKS = (
    "一行一符号", "按你的要求", "根据你发", "凑页数",
    "图里不要", "后端遮挡弧为虚线", "再编译一份", "我已经编译",
)
RULES = [
    ("editing-instruction", "error", re.compile(r"\s*".join(map(re.escape, phrase))),
     "核对是否把对话或制作指令写进了读者可见正文；确认后改写。")
    for phrase in LEAKS
]
RULES += [
    ("assistant-persona", "error",
     re.compile(r"\bas\s+an\s+AI\s+(?:language\s+)?model\b|作为\s*(?:一个\s*)?AI\s*(?:语言\s*)?模型[，,]", re.I),
     "检查助手自述是否进入正文；真实工具披露应描述实际使用情况。"),
    ("internal-artifact", "review",
     re.compile(r"\b(?:ANALYSIS_MODELING_REPORT|RESULTS_REPORT)\.md\b|\.mathmodel[/\\]paper[/\\]config\.json|(?<![^\s`{(])(?:qa|reports)[/\\][\w./\\-]+"),
     "确认这是必要的公开复现引用还是内部交接记录；不要用文件检查代替模型评价。"),
    ("production-note", "review",
     re.compile(r"本技能|穿帮|大面积留白|(?:正文|论文)(?:已经|已)?通过(?:所有|全部)?(?:验收|检查)"),
     "依据研究对象判断；研究术语或真实披露可保留，制作状态移到内部报告。"),
]
TEX_TOKEN = re.compile(r"%|\\begin\{(verbatim\*?|Verbatim|lstlisting|minted|comment)\}|\\appendix\b")
MD_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
MATH_SPAN = re.compile(r"(?s)(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$(?!\$).*?(?<!\\)\$(?!\$)|\\\(.*?\\\)|\\\[.*?\\\]")
TEX_LAYOUT = re.compile(r"(?s)\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|displaymath|math|tabular\*?|tabularx|table\*?|thebibliography)\}.*?\\end\{\1\}")
STYLE_RULES = (
    ("contrast-scaffold", re.compile(r"(?:不是|并非|不在于)[^。！？\n]{1,70}?(?:而是|而在于)"),
     "核对对举是否承担真实概念区分或替代解释；必要比较保留，空设误解才改成直接判断。"),
    ("prompt-like-colon", re.compile(r"(?:一句话(?:总结|概括)|核心是|换句话说)\s*[：:]"),
     "核对提示语是否提供范围或承接信息；删除无信息部分时保留判断、条件和证据。"),
    ("colloquial-preface", re.compile(r"(?:说白了|说穿了|先说结论)[，,:：]"),
     "核对是否为引用、研究对象或必要话语；普通论述可直接给出判断，保持学术语体。"),
    ("stacked-hedges", re.compile(r"可能\s*或许|或许\s*可能|\bmay\s+potentially\b|\bcould\s+possibly\b", re.I),
     "核对重复保留词的作用；保留实际不确定性，不能将相关、可能或区间结果改成确定因果。"),
)


def typst_comments(source: str) -> str:
    """Mask line/nested block comments while retaining quoted strings and offsets."""
    value, i, quoted = list(source), 0, False
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == '"':
            quoted = not quoted
        if not quoted and source.startswith("//", i) and (i == 0 or source[i-1] != ":"):
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            value[i:end] = _blank(source[i:end])
            i = end
            continue
        if not quoted and source.startswith("/*", i):
            start, depth = i, 1
            i += 2
            while i < len(source) and depth:
                if source.startswith("/*", i): depth += 1; i += 2
                elif source.startswith("*/", i): depth -= 1; i += 2
                else: i += 1
            value[start:i] = _blank(source[start:i])
            continue
        i += 1
    return "".join(value)


def prose_for_style(visible: str, suffix: str) -> str:
    """Additional lexical masking for editorial review, not a document renderer."""
    value = visible
    if suffix == ".tex":
        value = TEX_LAYOUT.sub(lambda m: _blank(m.group()), value)
    value = MATH_SPAN.sub(lambda m: _blank(m.group()), value)
    if suffix in {".md", ".typ"}:
        value = re.sub(r"(`+)[^`\n]+\1", lambda m: _blank(m.group()), value)
        # Headings, quotations, lists and tables have their own structural jobs.
        # Formal section/algorithm numbering is never treated as a style defect.
        value = "".join(_blank(line) if re.match(r"\s*(?:#{1,6}\s|={1,6}\s|>|\||[-*+]\s|\d+[.)]\s|!\[)", line) else line for line in value.splitlines(keepends=True))
    value = re.sub(r"https?://[^\s)<>]+", lambda m: _blank(m.group()), value)
    return value


def style_candidates(visible: str, suffix: str) -> list[dict]:
    prose = prose_for_style(visible, suffix)
    result = []
    for category, pattern, reason in STYLE_RULES:
        for match in pattern.finditer(prose):
            result.append(dict(start=match.start(), end=match.end(), category=category,
                               phrase=match.group(), reason=reason))
    paragraphs = list(re.finditer(r"\S.*?(?=\n\s*\n|\Z)", prose, re.S))
    for paragraph in paragraphs[1:]:
        match = re.match(r"(?:值得注意的是|需要指出的是|听起来|这意味着)[，,:：]?", paragraph.group())
        if match:
            result.append(dict(start=paragraph.start(), end=paragraph.start()+match.end(),
                               category="paragraph-reference", phrase=match.group(),
                               reason="核对段首评论的具体对象与证据衔接；已有清楚回指或必要限定时保留，不按词语直接删改。"))
    return result


def notation_review(visible: str, suffix: str) -> tuple[list[dict], list[dict]]:
    """Locate display endings and domain-note hints; does not infer mathematics."""
    spans = [(m.start(), m.end(), m.group()) for m in MATH_SPAN.finditer(visible)
             if m.group().startswith(('$$', r'\[')) or
             (suffix == '.typ' and m.group().startswith('$') and m.group()[1:2].isspace() and m.group()[-2:-1].isspace())]
    if suffix == '.tex':
        spans += [(m.start(), m.end(), m.group()) for m in TEX_LAYOUT.finditer(visible)
                  if m.group(1).rstrip('*') in {'equation','align','gather','multline','displaymath'}]
    # Nested display forms produce one location, not duplicate warnings.
    spans.sort(key=lambda item: (item[0], -item[1]))
    outer = []
    for item in spans:
        if not any(start <= item[0] and end >= item[1] for start,end,_ in outer):
            outer.append(item)
    findings, systems = [], []
    for start,end,body in outer:
        line_start=visible.rfind('\n',0,start)+1
        if suffix=='.md' and visible[line_start:start].lstrip().startswith('>'):
            continue
        following = visible[end:]
        match = re.match(r'[ \t]*(?:<[A-Za-z][\w:.-]*>[ \t]*)?([.。])[ \t]*(?=\n|$)', following)
        if match:
            findings.append(dict(start=end+match.start(1),end=end+match.end(1),
                                 category='formula-ending-period',phrase=match.group(1),
                                 reason='检查独立公式后的点号是否为多余装饰；保留小数、乘积、导数、省略号及明确格式所需标点，不自动改公式。'))
        internal=re.search(r'(?<![.\d])([.。])[ \t\r\n]*(?=(?:\\\]|\$\$|\$|\\end\{(?:equation\*?|align\*?|gather\*?|multline\*?|displaymath)\})$)',body)
        if internal:
            findings.append(dict(start=start+internal.start(1),end=start+internal.end(1),
                                 category='formula-ending-period',phrase=internal.group(1),
                                 reason='数学环境末尾有独立点号候选；逐式判断是否多余，不删除小数点、乘积点、导数点或省略号。修改公式后另做数学与渲染核验。'))
        if re.search(r'\\begin\{cases\}|\\left\s*\\\{[\s\S]*?\\begin\{aligned\}|\bcases\s*\(', body):
            note = following.lstrip()[:400].split('\n\n',1)[0]
            hint = bool(re.search(r'取值|定义域|变量域|变量范围|∈|\\in\b|\\mathbb|非负|正整数|实数|二元|整数|\\(?:geq?|leq?)\b|[A-Za-z_][^。\n]{0,12}[<>≤≥]|\b(?:domain|integer|binary|real-valued)\b',note,re.I))
            systems.append(dict(start=start,domain_note_hint=hint,variables_verified=False))
            if not hint:
                findings.append(dict(start=start,end=end,category='equation-domain-note',
                                     phrase='方程组或分段表达式',
                                     reason='核对公式后是否说明各变量的类型、取值范围、索引及适用域；题意未给出的界限不得补造。若为分段函数或已在式中完整定义，人工确认适用性。'))
    return findings, systems


def _blank(value: str) -> str:
    """Mask non-prose without changing source offsets or line numbers."""
    return "".join("\n" if c == "\n" else " " for c in value)


def visible_source(source: str, suffix: str, stop_at_appendix: bool = False) -> str:
    """A small lexical filter, not a TeX/Markdown renderer or include resolver."""
    if suffix == ".typ":
        return typst_comments(visible_source(source, ".md", stop_at_appendix))
    if suffix == ".tex":
        value = source
        pos = 0
        while m := TEX_TOKEN.search(value, pos):
            # An odd backslash count escapes %, an even count starts a comment.
            i = m.start() - 1
            while i >= 0 and value[i] == "\\":
                i -= 1
            if (m.start() - i - 1) % 2:
                pos = m.end()
                continue
            if m.group() == "%":
                end = value.find("\n", m.end())
                end = len(value) if end < 0 else end
            elif m.group(1):
                closing = "\\end{" + m.group(1) + "}"
                end = value.find(closing, m.end())
                end = len(value) if end < 0 else end + len(closing)
            elif stop_at_appendix:
                end = len(value)
            else:
                pos = m.end()
                continue
            value = value[:m.start()] + _blank(value[m.start():end]) + value[end:]
            pos = end
        return value

    result = []
    fence = None
    in_comment = False
    for line in source.splitlines(keepends=True):
        m = MD_FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line[m.end():].strip():
                fence = None
            result.append(_blank(line))
        elif m and not in_comment:
            fence = m.group(1)
            result.append(_blank(line))
        else:
            value = line
            pos = 0
            while pos < len(value):
                start = pos if in_comment else value.find("<!--", pos)
                if start < 0:
                    break
                end = value.find("-->", start if in_comment else start + 4)
                in_comment = end < 0
                end = len(value) if end < 0 else end + 3
                value = value[:start] + _blank(value[start:end]) + value[end:]
                pos = end
            result.append(value)
    return "".join(result)


def collect_files(paths: list[Path], exclude: tuple[str, ...] = ()) -> tuple[list[Path], list[Path]]:
    files, excluded = set(), set()
    for path in paths:
        if path.is_dir():
            candidates = (p for p in path.rglob("*") if p.suffix.lower() in {".tex", ".md", ".typ"})
            base = path
        elif path.is_file():
            if path.suffix.lower() not in {".tex", ".md", ".typ"}:
                raise ValueError(f"Unsupported source format: {path.suffix}")
            candidates, base = [path], path.parent
        else:
            raise FileNotFoundError(path)
        for item in candidates:
            relative = item.relative_to(base).as_posix()
            if any(fnmatch.fnmatchcase(relative, pattern.replace("\\", "/")) for pattern in exclude):
                excluded.add(item.resolve())
            else:
                files.add(item.resolve())
    # Explicit exclusions win even if overlapping roots selected the same file.
    files -= excluded
    if not files:
        raise ValueError("No TeX/Markdown sources selected after exclusions")
    return sorted(files), sorted(excluded)


def analyze(paths: list[Path], exclude: tuple[str, ...] = (), stop_at_appendix: bool = False, style_review: bool = False) -> dict:
    files, excluded = collect_files(paths, exclude)
    findings, equation_systems = [], []
    for path in files:
        raw = path.read_text(encoding="utf-8-sig")
        visible = visible_source(raw, path.suffix.lower(), stop_at_appendix)
        starts = [0] + [m.end() for m in re.finditer("\n", raw)]
        lines = raw.split("\n")
        for category, severity, pattern, reason in RULES:
            for m in pattern.finditer(visible):
                number = bisect_right(starts, m.start())
                findings.append({"path": str(path), "line": number,
                                 "phrase": re.sub(r"\s+", "", m.group()) if category == "editing-instruction" else m.group().strip(),
                                 "severity": severity, "category": category, "reason": reason,
                                 "excerpt": lines[number - 1].strip()[:160]})
        notation, systems = notation_review(visible, path.suffix.lower())
        equation_systems.extend({'path':str(path),'line':bisect_right(starts,item['start']),
                                 'domain_note_hint':item['domain_note_hint'],'variables_verified':False} for item in systems)
        editorial = style_candidates(visible,path.suffix.lower()) if style_review else []
        if notation or editorial:
            for item in notation+editorial:
                number = bisect_right(starts, item["start"])
                findings.append({"path": str(path), "line": number,
                                 "column": item["start"]-starts[number-1]+1,
                                 "phrase": item["phrase"], "severity": "review",
                                 "category": item["category"], "reason": item["reason"],
                                 "excerpt": lines[number-1].strip()[:160]})
    findings.sort(key=lambda item: (item["path"], item["line"], item["category"]))
    errors = sum(item["severity"] == "error" for item in findings)
    reviews = len(findings) - errors
    return {"passed": errors == 0, "review_required": bool(reviews),
            "error_count": errors, "review_count": reviews, "findings": findings,
            "checked_files": [str(p) for p in files], "excluded_files": [str(p) for p in excluded],
            "stop_at_appendix": stop_at_appendix, "style_review_enabled": style_review,
            "rewrites_text": False, "scope": "editorial_candidates_not_authorship_detection",
            "equation_systems": equation_systems}


def inspect(paths: list[Path], exclude: tuple[str, ...] = (), stop_at_appendix: bool = False) -> list[dict]:
    """Keep the existing findings-only API for callers."""
    return analyze(paths, exclude, stop_at_appendix)["findings"]


def main() -> int:
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Paper TeX/Typst/Markdown sources; includes are not expanded")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="Repeatable path glob relative to each selected directory (or a file's parent)")
    parser.add_argument("--stop-at-appendix", action="store_true",
                        help="Only when appendix is out of scope: stop each TeX source at a literal \\appendix")
    parser.add_argument("--style-review", action="store_true",
                        help="Also locate manual style-review candidates; never rewrites or infers authorship")
    args = parser.parse_args()
    try:
        report = analyze(args.paths, tuple(args.exclude), args.stop_at_appendix, args.style_review)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["findings"]:
            print(f"{item['path']}:{item['line']}: {item['severity'].upper()} {item['phrase']} | {item['reason']}")
        print(f"{'FAIL' if report['error_count'] else 'REVIEW' if report['review_required'] else 'PASS'} paper-voice check: "
              f"{report['error_count']} likely leaks, {report['review_count']} review candidates; "
              f"{len(report['checked_files'])} sources, {len(report['excluded_files'])} excluded")
    return 1 if report["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
