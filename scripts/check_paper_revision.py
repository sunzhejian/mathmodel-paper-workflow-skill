"""Read-only comparison of protected tokens in a local paper-style revision.

This is a lexical guard, not semantic equivalence or AI-authorship detection.
Exit 0: protected items match (read review_required); 1: protected items changed;
2: invalid/missing input. Does not write or automatically repair either source.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from check_paper_voice import MATH_SPAN, TEX_LAYOUT, visible_source

NUMBER = re.compile(r"(?<![A-Za-z0-9_])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?:[%％])?(?![0-9])")
UNIT = re.compile(r"(?<![A-Za-z0-9_])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?\s*(?:万元|小时|分钟|摄氏度|厘米|毫米|千克|公斤|千米|毫秒|元|秒|天|年|人|份|倍|吨|米|克|kPa|MPa|Pa|mL|kg|mg|mm|cm|km|ms|min|hours?|seconds?|minutes?|m/s|°C|℃|K|L|g|h|s|m)(?![A-Za-z])")
RELATION = re.compile(r"\\(?:leq?|geq?|neq|approx)\b|[<>≤≥≠≈=]")
CLAIM = re.compile(r"不显著|无显著|不超过|不小于|不大于|在[^。！？\n]{1,40}?条件下|可能|或许|尚未|未能|不能|无法|不支持|并非|不是|相关|关联|因果|显著|至少|至多|大于|小于|近似|约|\b(?:may|might|could|cannot|correlation|associated|causal|significant|approximately)\b", re.I)
CITATION = re.compile(r"\\(?:[Cc]ite[A-Za-z*]*|[Cc]ref|eqref|autoref|ref|label)\s*(?:\[[^]\n]*\]\s*)*\{[^}\n]*\}|(?<!\\)@[A-Za-z][\w:./-]*|\[\^?\d+\]|\[[^]\n]+\]\([^\n)]+\)")
DISCLOSURE = re.compile(r"AI\s*工具使用(?:声明|说明|详情)|AI\s*使用声明|人工智能工具使用(?:声明|情况说明)|AI\s+(?:Use\s+Statement|Usage\s+Disclosure|Tools\s+Disclosure)|Report\s+on\s+Use\s+of\s+AI", re.I)
DOMAIN_TERMS = re.compile(r"非负(?:实数|整数)?|非正(?:实数|整数)?|正整数|负整数|整数|实数|复数|二元(?:变量)?|二值(?:变量)?|实值|整数值|\b(?:nonnegative|non-negative|nonpositive|integer|integers|binary|real-valued|complex-valued)\b",re.I)
TEX_CODE = re.compile(r"(?s)\\begin\{(verbatim\*?|Verbatim|lstlisting|minted)\}.*?\\end\{\1\}")
HEADING = re.compile(r"(?m)^[ \t]*(?:#{1,6}\s+[^\n]+|={1,6}\s+[^\n]+|\\(?:subsubsection|subsection|section|chapter)\*?\s*\{[^\n]+)")


def fenced_blocks(raw: str) -> list[str]:
    result, start, marker, offset = [], None, None, 0
    for line in raw.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if start is None and match:
            start, marker = offset, match.group(1)
        elif start is not None and match and match.group(1)[0] == marker[0] and len(match.group(1)) >= len(marker) and not line[match.end():].strip():
            result.append(raw[start:offset+len(line)])
            start, marker = None, None
        offset += len(line)
    if start is not None:
        raise ValueError('Unclosed fenced block; establish source boundaries first')
    return result


def protected_tail(raw: str, visible: str, suffix: str) -> str | None:
    starts = []
    if suffix == '.tex':
        match = re.search(r"\\appendix\b", visible)
        if match:
            starts.append(match.start())
    for heading in HEADING.finditer(visible):
        if DISCLOSURE.search(heading.group()) or re.search(r"(?:^|[#=]\s*)(?:附录|Appendix\b)", heading.group(), re.I):
            starts.append(heading.start())
    return raw[min(starts):] if starts else None


def signature(raw: str, suffix: str) -> dict:
    visible = visible_source(raw, suffix)
    return {
        'numbers_in_order': NUMBER.findall(visible),
        'number_units_in_order': [re.sub(r'\s+', '', m.group()) for m in UNIT.finditer(visible)],
        'relations_in_order': RELATION.findall(visible),
        'math_in_order': [m.group() for m in MATH_SPAN.finditer(visible)],
        'references_in_order': CITATION.findall(visible),
        'urls_in_order': re.findall(r'https?://[^\s)<>]+',visible),
        'domain_terms_in_order': [m.group().lower() for m in DOMAIN_TERMS.finditer(visible)],
        'layout_in_order': [m.group() for m in TEX_LAYOUT.finditer(visible)] if suffix == '.tex' else [m.group() for m in re.finditer(r'(?m)^[ \t]*\|[^\n]*(?:\n[ \t]*\|[^\n]*)*', visible)],
        'headings_in_order': [m.group() for m in HEADING.finditer(visible)],
        'code_in_order': [m.group() for m in TEX_CODE.finditer(raw)] if suffix == '.tex' else fenced_blocks(raw),
        'protected_tail': protected_tail(raw, visible, suffix),
        'claim_cues': Counter(m.group().lower() for m in CLAIM.finditer(visible)),
    }


def compare(before: Path, after: Path) -> dict:
    before, after = Path(before), Path(after)
    suffix = before.suffix.lower()
    if suffix not in {'.tex', '.typ', '.md'} or suffix != after.suffix.lower():
        raise ValueError('Compare two sources in the same TeX/Typst/Markdown format')
    original = before.read_text(encoding='utf-8-sig')
    revised = after.read_text(encoding='utf-8-sig')
    a, b = signature(original, suffix), signature(revised, suffix)
    changed = [key for key in a if key != 'claim_cues' and a[key] != b[key]]
    cues = a['claim_cues'] != b['claim_cues']
    # Full protected values are intentionally absent from reports: code, appendix
    # and disclosure blocks can be private or much larger than the prose edit.
    return {
        'protected_passed': not changed, 'changed_protected_groups': changed,
        'review_required': bool(changed or cues),
        'claim_cues_changed': cues,
        'scope': 'lexical_protected_items_only', 'scientific_verified': False,
        'semantic_equivalence_verified': False, 'rewrites_text': False,
        'before': str(before.resolve()), 'after': str(after.resolve()),
        'checks': {key: {'unchanged': a[key] == b[key],
                         'before_items': len(a[key]) if isinstance(a[key], list) else int(a[key] is not None),
                         'after_items': len(b[key]) if isinstance(b[key], list) else int(b[key] is not None)}
                   for key in a if key != 'claim_cues'},
        'manual_review': ['核对数值对应的对象、比较基准、适用条件及因果方向；相同词项不证明含义相同。'] +
                         (['限定、否定或统计判断词发生变化，请逐句核对是否改变结论强度。'] if cues else []),
    }


def main() -> int:
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = compare(args.before, args.after)
    except (OSError, UnicodeError, ValueError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        label = 'FAIL' if not result['protected_passed'] else 'REVIEW' if result['review_required'] else 'PROTECTED ITEMS MATCH'
        print(label+'; scope='+result['scope'])
        if result['changed_protected_groups']:
            print('Changed: '+', '.join(result['changed_protected_groups']))
        for item in result['manual_review']:
            print(item)
    return 0 if result['protected_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
