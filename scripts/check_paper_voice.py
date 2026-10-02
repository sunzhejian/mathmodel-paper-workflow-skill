"""Locate workflow leakage in paper sources; leave scientific style to review."""
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


def _blank(value: str) -> str:
    """Mask non-prose without changing source offsets or line numbers."""
    return "".join("\n" if c == "\n" else " " for c in value)


def visible_source(source: str, suffix: str, stop_at_appendix: bool = False) -> str:
    """A small lexical filter, not a TeX/Markdown renderer or include resolver."""
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
            candidates = (p for p in path.rglob("*") if p.suffix.lower() in {".tex", ".md"})
            base = path
        elif path.is_file():
            if path.suffix.lower() not in {".tex", ".md"}:
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


def analyze(paths: list[Path], exclude: tuple[str, ...] = (), stop_at_appendix: bool = False) -> dict:
    files, excluded = collect_files(paths, exclude)
    findings = []
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
    findings.sort(key=lambda item: (item["path"], item["line"], item["category"]))
    errors = sum(item["severity"] == "error" for item in findings)
    reviews = len(findings) - errors
    return {"passed": errors == 0, "review_required": bool(reviews),
            "error_count": errors, "review_count": reviews, "findings": findings,
            "checked_files": [str(p) for p in files], "excluded_files": [str(p) for p in excluded],
            "stop_at_appendix": stop_at_appendix}


def inspect(paths: list[Path], exclude: tuple[str, ...] = (), stop_at_appendix: bool = False) -> list[dict]:
    """Keep the existing findings-only API for callers."""
    return analyze(paths, exclude, stop_at_appendix)["findings"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Paper TeX/Markdown sources; includes are not expanded")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="Repeatable path glob relative to each selected directory (or a file's parent)")
    parser.add_argument("--stop-at-appendix", action="store_true",
                        help="Only when appendix is out of scope: stop each TeX source at a literal \\appendix")
    args = parser.parse_args()
    try:
        report = analyze(args.paths, tuple(args.exclude), args.stop_at_appendix)
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
