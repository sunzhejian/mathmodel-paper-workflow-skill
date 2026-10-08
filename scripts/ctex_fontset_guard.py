"""Inspect a literal CTeX documentclass; adapt a NEW copy, never the input.

This checks an explicit declaration only. It does not execute TeX, discover
installed fonts, certify the PDF, or determine official competition rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

STRATEGIES = {"windows": "windows", "macos": "mac", "linux": "fandol"}
CTEX_CLASSES = {"ctexart", "ctexrep", "ctexbook"}
COMMAND = re.compile(r"(?<!\\)\\documentclass\b")


def without_comments(text):
    """Mask ordinary TeX comments while preserving all offsets/newlines."""
    result = list(text)
    i = 0
    while i < len(text):
        if text[i] == "%":
            slashes, j = 0, i - 1
            while j >= 0 and text[j] == "\\":
                slashes += 1
                j -= 1
            if slashes % 2 == 0:
                while i < len(text) and text[i] not in "\r\n":
                    result[i] = " "
                    i += 1
                continue
        i += 1
    return "".join(result)


def group(text, position, opening, closing):
    if position >= len(text) or text[position] != opening:
        raise ValueError("Expected a literal documentclass group")
    depth = 1
    start = position + 1
    for end in range(start, len(text)):
        if text[end] == opening and (end == 0 or text[end - 1] != "\\"):
            depth += 1
        elif text[end] == closing and (end == 0 or text[end - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return start, end, end + 1
    raise ValueError("Unclosed documentclass group; inspect source manually")


def declaration(text):
    clean = without_comments(text)
    preamble = re.split(r"(?<!\\)\\begin\s*\{document\}", clean, maxsplit=1)[0]
    if re.search(r"\\(?:catcode|def\s*\\documentclass|let\s*\\documentclass)\b", preamble):
        raise ValueError("Custom TeX tokenization/documentclass definitions need manual review")
    matches = list(COMMAND.finditer(preamble))
    if len(matches) != 1:
        raise ValueError("Require one unambiguous literal documentclass in the preamble")
    match = matches[0]
    # A declaration inside a macro/group is not proof that it is invoked.
    prefix = preamble[:match.start()]
    if prefix.count("{") != prefix.count("}"):
        raise ValueError("A nested documentclass needs manual review")
    pos = match.end()
    while pos < len(preamble) and preamble[pos].isspace():
        pos += 1
    option_start, option_end = pos, pos
    if pos < len(preamble) and preamble[pos] == "[":
        option_start, option_end, pos = group(preamble, pos, "[", "]")
    while pos < len(preamble) and preamble[pos].isspace():
        pos += 1
    class_start, class_end, _ = group(preamble, pos, "{", "}")
    name = preamble[class_start:class_end].strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise ValueError("Macro-expanded class names need manual review")
    options = preamble[option_start:option_end]
    found = list(re.finditer(r"(?:^|,)\s*fontset\s*=\s*(\{[^{}]*\}|[^,]*)", options))
    if len(found) > 1:
        raise ValueError("Duplicate fontset options are ambiguous")
    value, span = None, None
    if found:
        raw = found[0].group(1)
        value = raw.strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
            raise ValueError("Macro/computed fontset needs manual review")
        left, right = found[0].span(1)
        left += len(raw) - len(raw.lstrip())
        right -= len(raw) - len(raw.rstrip())
        span = (option_start + left, option_start + right)
    if re.search(r"\\PassOptionsTo(?:Class|Package)\b", preamble):
        raise ValueError("Forwarded options may override the declaration; inspect the actual class/package")
    return {"class": name, "fontset": value, "value_span": span,
            "declaration_line": text.count("\n", 0, match.start()) + 1,
            "ctex_package": bool(re.search(r"\\(?:usepackage|RequirePackage)(?:\s*\[[^]]*\])?\s*\{[^}]*\bctex\b[^}]*\}", preamble))}


def inspect(path, platform):
    if platform not in STRATEGIES:
        raise ValueError("Choose windows, macos or linux explicitly")
    path = Path(path)
    raw = path.read_bytes()
    result = {"source_sha256": hashlib.sha256(raw).hexdigest(), "platform": platform,
              "suggested_fontset": STRATEGIES[platform], "compilation": "not_run",
              "needs_compile_and_visual_check": True,
              "scope": "Literal CTeX declaration only; not installed fonts, PDF typography or official-rule compliance"}
    try:
        parsed = declaration(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        return {**result, "status": "review_required", "reason": str(exc)}
    result.update({k: v for k, v in parsed.items() if k != "value_span"})
    if parsed["class"] not in CTEX_CLASSES:
        return {**result, "status": "review_required" if parsed["fontset"] or parsed["ctex_package"] else "not_applicable",
                "reason": "Custom class/package font configuration is not automatically adapted"}
    if parsed["fontset"] is None:
        return {**result, "status": "review_required", "reason": "No explicit fontset; CTeX may select its platform default. Check the actual engine and fonts"}
    if parsed["fontset"] not in {"windows", "mac", "fandol"}:
        return {**result, "status": "review_required", "reason": "Preserve explicitly chosen custom/none font configuration"}
    return {**result, "status": "declaration_matches_strategy" if parsed["fontset"] == STRATEGIES[platform] else "declaration_mismatch"}


def adapt(path, platform, output):
    result = inspect(path, platform)
    if result["status"] not in {"declaration_mismatch", "declaration_matches_strategy"}:
        raise ValueError(result.get("reason", "Declaration is unsupported for adaptation"))
    path, output = Path(path).resolve(), Path(output).absolute()
    if path == output.resolve() or output.exists() or output.is_symlink():
        raise ValueError("Output must be a NEW source copy; never replace input, old paper or an existing file")
    if any(p.is_symlink() for p in (output.parent, *output.parent.parents)):
        raise ValueError("A linked output parent is not supported")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != result["source_sha256"]:
        raise ValueError("Input changed during adaptation; inspect its new version first")
    text = raw.decode("utf-8")
    parsed = declaration(text)
    left, right = parsed["value_span"]
    revised = text[:left] + STRATEGIES[platform] + text[right:]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(revised.encode("utf-8"))
    checked = inspect(output, platform)
    if checked["status"] != "declaration_matches_strategy":
        raise ValueError("Written declaration did not match; preserve both sources for review")
    return {**checked, "output": str(output), "input_sha256": result["source_sha256"],
            "changed": revised != text, "source_input_preserved": path.read_bytes() == raw}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "adapt"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--platform", required=True, choices=tuple(STRATEGIES))
    parser.add_argument("--output", type=Path, help="Required NEW source path in adapt mode")
    args = parser.parse_args()
    try:
        if args.mode == "adapt":
            if args.output is None:
                raise ValueError("adapt requires --output with a new source path")
            result = adapt(args.source, args.platform, args.output)
        else:
            if args.output is not None:
                raise ValueError("inspect is read-only; no --output")
            result = inspect(args.source, args.platform)
        print(json.dumps(result, ensure_ascii=False))
        return {"declaration_mismatch": 1, "review_required": 2}.get(result["status"], 0)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
