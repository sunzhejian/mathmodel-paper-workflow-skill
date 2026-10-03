"""Locate fragmented Typst equations without changing a manuscript.

This is a bounded structural lint, not a Typst parser or mathematical proof.
It checks literal dollar equations in the supplied source, and measured text
rows in an optional PDF. Imports, custom macros and rasterized math need review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pymupdf

from rendering_guard import _visible_code


_ATOM = re.compile(
    r'^(?:[A-Za-zα-ωΑ-Ω]|alpha|beta|gamma|delta|theta|rho|sigma|phi|psi|omega|tau)'
    r'(?:_(?:\([^()]{1,40}\)|[A-Za-z0-9]+))?(?:\^(?:\([^()]{1,40}\)|[A-Za-z0-9]+))?$'
)
_ACCENT_ATOM = re.compile(r'^(?:hat|bar|tilde|vec)\(([A-Za-zα-ωΑ-Ω])\)(?:_(?:\([^()]{1,40}\)|[A-Za-z0-9]+))?$')
_ORPHAN = re.compile(r'^(?:[=+−\-*/×÷(),，:：;；]+|=?\s*(?:min|max)\s*\(|[+−\-]\s*[A-Za-z]\s*[−+\-])$')


def _position(text, offset):
    return {'line': text.count('\n', 0, offset) + 1,
            'column': offset - text.rfind('\n', 0, offset)}


def _atomic(body):
    compact = re.sub(r'\s+', '', body)
    return bool(_ATOM.fullmatch(compact) or _ACCENT_ATOM.fullmatch(compact))


def _separator_text(fragment):
    """Decode only literal #text strings; unknown expressions remain visible."""
    def decode(match):
        try:
            return json.loads(match[1])
        except ValueError:
            return match[0]
    fragment = re.sub(r'#text\s*\(\s*("(?:\\.|[^"\\])*")\s*\)', decode, fragment)
    return fragment.strip()


def _report(issues, **evidence):
    errors = any(item['severity'] == 'error' for item in issues)
    warnings = any(item['severity'] == 'warning' for item in issues)
    status = 'fail' if errors else 'review' if warnings else 'pass'
    return dict(status=status, passed=status == 'pass', review_required=errors or warnings,
                issues=issues, **evidence)


def check_source(text: str, source_name='<memory>', *, stop_at_heading=None):
    """Inspect literal Typst source. No file, formula, punctuation or number is edited."""
    original = text
    if stop_at_heading is not None:
        if not isinstance(stop_at_heading, str) or not stop_at_heading.strip():
            raise ValueError('stop_at_heading must be a nonempty exact heading')
        boundary = re.search(r'(?m)^=+\s+' + re.escape(stop_at_heading) + r'\s*$', text)
        if boundary is None:
            raise ValueError('Declared stop heading was not found')
        text = text[:boundary.start()]
    issues, equations = [], []
    try:
        visible = _visible_code(text)
    except ValueError as exc:
        return _report([{'code': 'source_lexing_incomplete', 'severity': 'warning',
                         'message': str(exc), 'source': source_name}],
                       source=source_name, source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                       equations=[], coverage='Source could not be safely scanned; compile and review it.')
    offsets = []
    # Escaping depends on parity, not merely a backslash immediately before $.
    for offset, char in enumerate(visible):
        if char != '$':
            continue
        count, previous = 0, offset - 1
        while previous >= 0 and visible[previous] == '\\':
            count += 1
            previous -= 1
        if count % 2 == 0:
            offsets.append(offset)
    if len(offsets) % 2:
        issues.append({'code': 'unmatched_math_delimiter', 'severity': 'warning',
                       **_position(text, offsets[-1]), 'message': 'Unpaired literal math delimiter; source scan is incomplete.'})
    # Explicit block defaults can promote otherwise proper inline $x$ too.
    forced = []
    for match in re.finditer(r'(?:#set\s+|\bset\s+)math\.equation\s*\(([^()]*)\)', visible, re.S):
        if re.search(r'\bblock\s*:\s*true\b', match[1]):
            forced.append(_position(text, match.start()))
    if forced:
        issues.append({'code': 'equation_block_default', 'severity': 'warning',
                       'locations': forced,
                       'message': 'A block:true equation default may turn inline variables into displays; inspect its actual scope and PDF.'})
    for start, end in zip(offsets[::2], offsets[1::2]):
        body = text[start + 1:end]
        natural_display = bool(body and body[0].isspace() and body[-1].isspace())
        equations.append({'start': start, 'end': end + 1, **_position(text, start),
                          'body': body.strip(), 'natural_display': natural_display,
                          'atomic': _atomic(body),
                          'display_basis': 'whitespace on both delimiter boundaries' if natural_display else 'inline syntax'})
    groups = []
    for eq in equations:
        if not eq['natural_display']:
            continue
        if not groups or re.search(r'\n\s*\n', visible[groups[-1][-1]['end']:eq['start']]):
            groups.append([eq])
        else:
            groups[-1].append(eq)
    for group in groups:
        atoms = [eq for eq in group if eq['atomic']]
        if len(atoms) < 2:
            continue
        separators = [_separator_text(text[left['end']:right['start']])
                      for left, right in zip(group, group[1:])]
        orphans = [value for value in separators if _ORPHAN.fullmatch(value)]
        if orphans:
            issues.append({'code': 'fragmented_relation', 'severity': 'error',
                           'source': source_name, 'locations': [{key: eq[key] for key in ('line', 'column', 'body')} for eq in atoms],
                           'orphan_separators': orphans,
                           'message': 'A relation is split into numbered display variables while operators/functions remain outside math. Keep the entire relation in one math element; use $x_t$ for inline variables.'})
        elif len(atoms) >= 3:
            issues.append({'code': 'display_variable_cluster', 'severity': 'warning',
                           'locations': [{key: eq[key] for key in ('line', 'column', 'body')} for eq in atoms],
                           'message': 'Several atomic variables are separate display elements inside one paragraph; verify that these were intentionally displayed rather than inline references.'})
    return _report(issues, source=source_name,
                   source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                   checked_characters=len(text), stop_at_heading=stop_at_heading,
                   equation_count=len(equations), display_count=sum(eq['natural_display'] for eq in equations),
                   atomic_display_count=sum(eq['natural_display'] and eq['atomic'] for eq in equations),
                   block_defaults=forced, equations=equations,
                   coverage='Literal dollar math in this file only. Strings, comments and raw code examples are excluded. Import/macro evaluation, custom show transforms, mathematical correctness and all other typesetting are not verified.')


def _pdf_lines(page):
    lines = []
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    for block in page.get_text('dict', flags=flags)['blocks']:
        for line in block.get('lines', []):
            spans = [span for span in line.get('spans', []) if span.get('text', '').strip()]
            if not spans:
                continue
            original = ''.join(span['text'] for span in spans).strip()
            normalized = unicodedata.normalize('NFKC', original)
            lines.append({'text': original, 'normalized': re.sub(r'\s+', '', normalized),
                          'bbox': [round(v, 3) for v in line['bbox']],
                          'size': max(span['size'] for span in spans),
                          'fonts': sorted({span['font'] for span in spans})})
    return sorted(lines, key=lambda item: (item['bbox'][1], item['bbox'][0]))


def check_pdf(path: Path, *, page_numbers=None):
    """Flag suspicious runs of centered atomic rows, equation numbers and operators.

    Numbered short but complete equations (x=0) do not match atomic rows. Bare
    variables with no surrounding orphan operators produce a review, not a
    mathematical-error assertion. Raster-only pages are explicitly unverified.
    """
    issues, candidates, checked, unreadable = [], [], [], []
    with pymupdf.open(path) as document:
        pages = len(document)
        selected = list(range(1, pages + 1)) if page_numbers is None else list(page_numbers)
        if (not selected or len(set(selected)) != len(selected)
                or any(type(n) is not int or not 1 <= n <= pages for n in selected)):
            raise ValueError('page_numbers must contain distinct existing one-based pages')
        for page_number in selected:
            page = document[page_number - 1]
            lines = _pdf_lines(page)
            checked.append(page_number)
            if not lines:
                unreadable.append(page_number)
                continue
            numbers = [line for line in lines
                       if re.fullmatch(r'[（(]\d+(?:[.\-]\d+)*[）)]', line['normalized'])
                       and line['bbox'][0] > page.rect.width * .65]
            atoms = []
            for line in lines:
                text = line['normalized']
                box = line['bbox']
                if (not re.fullmatch(r'[A-Za-zα-ωΑ-Ω](?:[A-Za-z0-9−+\-]{0,5})', text)
                        or box[2] - box[0] > 90
                        or abs((box[0] + box[2]) / 2 - page.rect.width / 2) > page.rect.width * .10):
                    continue
                matching = [num for num in numbers if abs(num['bbox'][1] - box[1]) <= max(5, line['size'] * .45)]
                if matching:
                    atoms.append(dict(line, page=page_number, number=matching[0]['text'], number_bbox=matching[0]['bbox']))
            groups = []
            for atom in atoms:
                if not groups or atom['bbox'][1] - groups[-1][-1]['bbox'][3] > 100:
                    groups.append([atom])
                else:
                    groups[-1].append(atom)
            for group in groups:
                if len(group) < 3:
                    continue
                top, bottom = group[0]['bbox'][1] - 60, group[-1]['bbox'][3] + 30
                orphan_lines = [line for line in lines if top <= line['bbox'][1] <= bottom
                                and _ORPHAN.fullmatch(line['normalized'])
                                and line['bbox'][0] < page.rect.width * .35]
                severity = 'error' if len(orphan_lines) >= 2 else 'warning'
                candidates.extend(group)
                issues.append({'code': 'pdf_fragmented_equation_run' if severity == 'error' else 'pdf_numbered_atomic_run',
                               'severity': severity, 'page': page_number,
                               'equation_rows': group, 'orphan_operator_rows': orphan_lines,
                               'message': 'Measured PDF contains repeated centered atomic rows with individual equation numbers' +
                                          (' and detached operators/functions. Inspect the cited source paragraph before accepting the manuscript.' if severity == 'error' else '; review whether these intentionally represent independent equations.')})
    if unreadable:
        issues.append({'code': 'pdf_text_unavailable', 'severity': 'warning', 'pages': unreadable,
                       'message': 'No extractable text on these pages; raster math needs visual review.'})
    return _report(issues, pdf=str(path), pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   pages=pages, checked_pages=checked, atomic_numbered_rows=candidates,
                   coverage='Measured text rows, locations and numbering patterns only; no theorem proving, equation-to-source mapping, raster OCR or universal layout validation.')


def check(source: Path, pdf: Path | None = None, *, stop_at_heading=None, page_numbers=None):
    source_report = check_source(source.read_text(encoding='utf-8-sig'), str(source), stop_at_heading=stop_at_heading)
    pdf_report = check_pdf(pdf, page_numbers=page_numbers) if pdf else None
    reports = [source_report] + ([pdf_report] if pdf_report else [])
    status = 'fail' if any(r['status'] == 'fail' for r in reports) else 'review' if any(r['status'] == 'review' for r in reports) else 'pass'
    return {'schema_version': 1, 'status': status, 'passed': status == 'pass',
            'review_required': status != 'pass', 'source_check': source_report,
            'pdf_check': pdf_report, 'source_file_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'manuscript_modified': False,
            'scope': 'Structural formula integrity diagnostic. A pass means no supported pattern was found, not complete mathematical or typesetting certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--stop-at-heading', help='Exact Typst heading before excluded appendices')
    parser.add_argument('--pages', help='Explicit one-based PDF pages, for example 1,2,3')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        for input_path in [args.source] + ([args.pdf] if args.pdf else []):
            if (args.output.resolve() == input_path.resolve()
                    or args.output.exists() and input_path.exists() and args.output.samefile(input_path)):
                parser.error('The diagnostic output must not overwrite or alias a manuscript input.')
    pages = [int(value) for value in args.pages.split(',')] if args.pages else None
    report = check(args.source, args.pdf, stop_at_heading=args.stop_at_heading, page_numbers=pages)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)
    return 0 if report['passed'] else 1 if report['status'] == 'fail' else 2


if __name__ == '__main__':
    raise SystemExit(main())
