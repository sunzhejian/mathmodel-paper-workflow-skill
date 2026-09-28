"""Flag high-confidence workflow phrases leaked into paper prose or captions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


# Deliberately small. These phrases describe the collaboration or layout task,
# not the modeled object. A pass is not a full editorial review.
LEAKS = (
    "一行一符号", "按你的要求", "按用户要求", "根据你发",
    "这次试运行", "本次试运行", "穿帮", "凑页数",
    "大面积留白", "图里不要", "后端遮挡弧为虚线",
    "再编译一份", "我已经编译", "用户指定", "本技能",
)
COMMENT = re.compile(r"(?<!\\)%.*$")


def inspect(paths: list[Path]) -> list[dict]:
    findings = []
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in path.rglob("*") if p.suffix.lower() in {".tex", ".md"})
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(path)
    for path in sorted(set(files)):
        for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = COMMENT.sub("", raw) if path.suffix.lower() == ".tex" else raw
            for phrase in LEAKS:
                if phrase in line:
                    findings.append({"path": str(path), "line": number, "phrase": phrase,
                                     "excerpt": line.strip()[:160]})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Paper TeX/Markdown files or directories")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        findings = inspect(args.paths)
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"passed": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"{item['path']}:{item['line']}: {item['phrase']} | {item['excerpt']}")
        print(f"{'PASS' if not findings else 'FAIL'} paper-voice check: {len(findings)} high-confidence leaks")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
