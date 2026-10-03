"""Check explicitly contracted summary boundaries; repair simple Typst sources.

No competition-wide default is inferred. Native macro templates should retain
their own abstract/pagebreak rules. A PDF check never edits scientific text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import pymupdf
from rendering_guard import _visible_code


def validate_summary_contract(contract):
    fields = {'separate_page', 'max_pages', 'heading', 'body_heading'}
    if not isinstance(contract, dict) or set(contract) != fields:
        raise ValueError('Summary contract must declare separate_page, max_pages, heading and body_heading')
    if not isinstance(contract['separate_page'], bool):
        raise ValueError('Summary separate_page must be boolean')
    if type(contract['max_pages']) is not int or contract['max_pages'] < 1:
        raise ValueError('Summary max_pages must be a positive integer')
    for field in ('heading', 'body_heading'):
        value = contract[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 200 or '\n' in value or '\r' in value:
            raise ValueError('Summary ' + field + ' must be a nonempty single-line title')
    if _compact(contract['heading']) == _compact(contract['body_heading']):
        raise ValueError('Summary and body titles must be distinct')
    return contract


def _compact(text):
    return re.sub(r'\s+', '', text)


def _matches_heading(line, heading):
    text, target = _compact(line), _compact(heading)
    if text == target:
        return True
    prefix = r'(?:[0-9]+(?:[.．][0-9]+)*[.．、]?|[一二三四五六七八九十百]+[、.．]?|第[一二三四五六七八九十百0-9]+[章节])'
    return re.fullmatch(prefix + re.escape(target), text) is not None


def _pdf_lines(doc):
    lines = []
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    for page_number, page in enumerate(doc, 1):
        for block in page.get_text('dict', flags=flags)['blocks']:
            for line in block.get('lines', []):
                spans = [span for span in line['spans'] if span.get('text', '').strip()]
                if not spans:
                    continue
                text = ''.join(span['text'] for span in line['spans']).strip()
                sizes = sorted({round(span['size'], 3) for span in spans})
                lines.append({'page': page_number, 'text': text,
                              'font_sizes_pt': sizes, 'maximum_font_size_pt': max(sizes),
                              'fonts': sorted({span['font'] for span in spans}),
                              'bbox': [round(value, 3) for value in line['bbox']]})
    return sorted(lines, key=lambda item: (item['page'], item['bbox'][1], item['bbox'][0]))


def _position(line):
    return line['page'], line['bbox'][1], line['bbox'][0]


def check_pdf(pdf: Path, summary_contract):
    contract = validate_summary_contract(summary_contract)
    with pymupdf.open(pdf) as doc:
        lines = _pdf_lines(doc)
        pages = len(doc)
    summaries = [line for line in lines if _matches_heading(line['text'], contract['heading'])]
    bodies = [line for line in lines if _matches_heading(line['text'], contract['body_heading'])]
    report = {
        'passed': False, 'status': 'pending', 'pages': pages,
        'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'summary_page': None, 'summary_end_page': None, 'body_page': None,
        'summary_pages': None, 'summary_pages_lower_bound': None,
        'same_page': None, 'overflow': None,
        'matches': {'summary': summaries, 'body': bodies, 'keywords': []},
        'issues': [],
        'scope': 'exact standalone title lines with measured fonts and explicit keyword boundary; checks page separation/count only, not scientific content, font roles or all contest requirements',
    }
    for name, candidates in (('summary', summaries), ('body', bodies)):
        if len(candidates) != 1:
            report['issues'].append(name + ' title missing or ambiguous: ' + str(len(candidates)) + ' matching independent lines')
    if report['issues']:
        return report
    summary, body = summaries[0], bodies[0]
    report.update(summary_page=summary['page'], body_page=body['page'])
    if _position(body) <= _position(summary):
        report['status'] = 'fail'
        report['issues'].append('Body title does not follow summary title')
        return report
    keywords = [line for line in lines
                if _position(summary) < _position(line) < _position(body)
                and re.match(r'^关键(?:词|字)\s*[:：]', line['text'])]
    report['matches']['keywords'] = keywords
    report['summary_pages_lower_bound'] = max(1, body['page'] - summary['page'])
    if summary['page'] == body['page']:
        report.update(summary_pages=1, same_page=True, overflow=1 > contract['max_pages'])
    elif len(keywords) == 1:
        end_page = keywords[0]['page']
        span_pages = end_page - summary['page'] + 1
        report.update(summary_end_page=end_page, summary_pages=span_pages,
                      same_page=end_page == body['page'], overflow=span_pages > contract['max_pages'])
    else:
        report['issues'].append('Summary end boundary missing or ambiguous; title pages alone cannot prove where summary content ends')
        if report['summary_pages_lower_bound'] > contract['max_pages']:
            report['status'] = 'fail'
            report['overflow'] = True
        return report
    if contract['separate_page'] and report['same_page']:
        report['issues'].append('Summary and first body chapter share a page')
    if report['overflow']:
        report['issues'].append('Summary exceeds contracted maximum of ' + str(contract['max_pages']) + ' page(s)')
    report['passed'] = not report['issues']
    report['status'] = 'pass' if report['passed'] else 'fail'
    return report


def _top_level_lines(masked):
    lines = []
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    offset = 0
    for line in masked.splitlines(keepends=True):
        if not stack:
            lines.append((offset, line))
        for char in line:
            if char in pairs:
                stack.append(pairs[char])
            elif char in ')]}':
                if not stack or stack.pop() != char:
                    raise ValueError('Unbalanced source; inspect native template instead of guessing')
        offset += len(line)
    if stack:
        raise ValueError('Unbalanced source; inspect native template instead of guessing')
    return lines


def _top_level_headings(masked):
    headings = []
    for offset, line in _top_level_lines(masked):
        match = re.match(r'^[ \t]*=[ \t]+([^\r\n]+)', line)
        if match:
            headings.append((offset, match[1].strip()))
    return headings


def _summary_marker(line, heading):
    target = _compact(heading)
    if _compact(line).strip('*') == target:
        return True
    if re.match(r'^\s*#(?:align|text|block)\b', line):
        return any(_compact(part).strip('*') == target for part in re.findall(r'\[([^\[\]\n]*)\]', line))
    return False


def ensure_separation(source: Path, summary_contract):
    contract = validate_summary_contract(summary_contract)
    before = source.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    if not contract['separate_page']:
        return {'changed': False, 'status': 'not_required', 'inserted_pagebreak': False,
                'before_sha256': before_hash, 'after_sha256': before_hash,
                'scope': 'separate_page disabled by explicit contract; source unchanged'}
    if source.suffix.lower() != '.typ':
        raise ValueError('Automatic separation supports simple Typst sources only; retain the native template rule')
    text = before.decode('utf-8-sig')
    masked = _visible_code(text)
    headings = _top_level_headings(masked)
    matches = [entry for entry in headings if _matches_heading(entry[1], contract['body_heading'])]
    if len(matches) != 1 or not headings or headings[0] != matches[0]:
        raise ValueError('Need one matching first top-level = body title; inspect native template instead of guessing')
    body_offset = matches[0][0]
    prefix = masked[:body_offset]
    if re.search(r'^\s*#(?:import|include)\b', prefix, re.M):
        raise ValueError('Imported summary/template needs its native pagebreak rule; automatic insertion refused')
    summary_markers, keyword_markers = [], []
    for offset, line in _top_level_lines(prefix):
        if _summary_marker(line, contract['heading']):
            summary_markers.append(offset)
        if re.search(r'(?:^|\[)\s*\*{0,2}关键(?:词|字)\*{0,2}\s*[:：]', line):
            keyword_markers.append((offset, offset + len(line)))
    if len(summary_markers) != 1 or len(keyword_markers) != 1 or keyword_markers[0][0] <= summary_markers[0]:
        raise ValueError('Need unambiguous active summary and following keywords before body title; do not infer macro contents')
    gap = prefix[keyword_markers[0][1]:].strip()
    existing = re.fullmatch(r'#pagebreak\s*\(\s*\)', gap) is not None
    if gap and not existing:
        raise ValueError('Unsupported content between keywords and body; inspect native summary template')
    newline = '\r\n' if '\r\n' in text else '\n'
    updated = text if existing else text[:body_offset] + '#pagebreak()' + newline + newline + text[body_offset:]
    after = (b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b'') + updated.encode('utf-8')
    if after != before:
        source.write_bytes(after)
    return {
        'changed': after != before, 'status': 'unchanged' if existing else 'applied',
        'inserted_pagebreak': not existing, 'body_heading': contract['body_heading'],
        'source_line': text[:body_offset].count('\n') + 1,
        'before_sha256': before_hash, 'after_sha256': hashlib.sha256(after).hexdigest(),
        'scope': 'one strong pagebreak before explicitly matched first body title; all existing source bytes/scientific text preserved; compile and check actual PDF next',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for action in ('check', 'apply'):
        child = commands.add_parser(action)
        child.add_argument('file', type=Path)
        child.add_argument('--contract', required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding='utf-8-sig'))
    result = check_pdf(args.file, contract) if args.action == 'check' else ensure_separation(args.file, contract)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('passed') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
