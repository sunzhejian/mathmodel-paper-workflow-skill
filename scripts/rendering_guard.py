"""Target-aware SVG/font checks and a declared Typst font profile.

Family embedding/use does not establish paragraph roles, glyph correctness,
diagram meaning or full manuscript quality. Inspect the actual PDF, too.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import pymupdf


def svg_compatibility(path: Path, engine='typst') -> dict:
    if engine not in {'typst', 'browser'}:
        raise ValueError('Unsupported SVG target engine')
    data = path.read_text(encoding='utf-8-sig')
    root = ET.fromstring(data)
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('Expected an SVG root element')
    reasons, styles, external = [], [], []
    css_attributes = {'style', 'fill', 'stroke', 'filter', 'clip-path', 'mask',
                      'marker', 'marker-start', 'marker-mid', 'marker-end',
                      'font-family', 'color', 'stop-color', 'flood-color',
                      'lighting-color', 'cursor'}
    for node in root.iter():
        tag = node.tag.rsplit('}', 1)[-1]
        if engine == 'typst' and tag == 'foreignObject':
            reasons.append('foreignObject/HTML labels are not a portable Typst SVG input')
        if tag == 'style':
            styles.append(''.join(node.itertext()))
        for name, value in node.attrib.items():
            local_name = name.rsplit('}', 1)[-1]
            # An a[href] is a hyperlink; it does not fetch rendering resources.
            if (tag in {'image', 'use', 'feImage'} and local_name in {'href', 'src'}
                    and value.strip() and not value.strip().lower().startswith(('#', 'data:'))):
                external.append(value)
            if local_name in css_attributes:
                styles.append(value)
    css = re.sub(r'/\*.*?\*/', '', '\n'.join(styles), flags=re.S)
    if engine == 'typst' and re.search(r'\b(?:light-dark|var)\s*\(', css, re.I):
        reasons.append('dynamic CSS colors require a target renderer check')
    for match in re.finditer(r'\burl\s*\(\s*([\'"]?)(.*?)\1\s*\)', css, re.I | re.S):
        value = match[2].strip()
        if value and not value.lower().startswith(('#', 'data:')):
            external.append(value)
    if re.search(r'@import\b', css, re.I):
        external.append('CSS @import')
    # ElementTree omits processing instructions, including linked stylesheets.
    if re.search(r'<\?xml-stylesheet\b', re.sub(r'<!--.*?-->', '', data, flags=re.S), re.I):
        external.append('xml-stylesheet')
    if external:
        reasons.append('external resources are not bundled: ' + ', '.join(sorted(set(external))))
    reasons = list(dict.fromkeys(reasons))
    return {
        'asset': path.name, 'target_engine': engine,
        'direct_embedding_ready': not reasons, 'reasons': reasons,
        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'scope': 'known portability hazards only; actual visual rendering and scientific meaning require review',
        'next_step': ('Use portable SVG or export a high-resolution PNG from this same editable source; keep vector/editable originals'
                      if reasons else 'Check actual final-PDF rendering at the declared size'),
    }


def font_names(compiler: Path, font_dir: Path | None = None, *, env=None):
    args = [str(compiler), 'fonts']
    if font_dir:
        args += ['--font-path', str(font_dir)]
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=45, check=True, env=env)
    return {name.strip() for name in p.stdout.splitlines() if name.strip()}


def validate_contract(contract):
    fields = {'schema_version', 'engine', 'fonts', 'body_size_pt', 'margins_cm',
              'minimum_pages', 'figure_width_mm', 'minimum_dpi', 'summary'}
    if not isinstance(contract, dict) or set(contract) - fields:
        raise ValueError('Unsupported rendering contract field')
    if type(contract.get('schema_version')) is not int or contract['schema_version'] != 1 or contract.get('engine') != 'typst':
        raise ValueError('This renderer supports a declared Typst v1 contract')
    fonts = contract.get('fonts', {})
    if (not isinstance(fonts, dict) or set(fonts) != {'body', 'heading', 'latin'}
            or not all(isinstance(v, str) and 0 < len(v.strip()) < 100 for v in fonts.values())):
        raise ValueError('Declare body, heading and Latin font families')
    for field in ['body_size_pt', 'margins_cm', 'figure_width_mm', 'minimum_dpi']:
        value = contract.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Positive finite ' + field + ' required')
    n = contract.get('minimum_pages')
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
        raise ValueError('Invalid minimum page count')
    return contract


def _visible_code(text):
    """Mask strings/comments/raw examples while retaining source offsets."""
    out = list(text)
    i = 0
    while i < len(text):
        start = i
        if text.startswith('//', i):
            i = text.find('\n', i)
            if i < 0:
                i = len(text)
        elif text.startswith('/*', i):
            i += 2
            depth = 1
            while i < len(text) and depth:
                if text.startswith('/*', i):
                    depth += 1
                    i += 2
                elif text.startswith('*/', i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError('Unterminated Typst block comment')
        elif text[i] == '"':
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise ValueError('Unterminated Typst string')
        elif text[i] == '`':
            length = 1
            while i + length < len(text) and text[i + length] == '`':
                length += 1
            end = text.find('`' * length, i + length)
            if end < 0:
                raise ValueError('Unterminated Typst raw text')
            i = end + length
        else:
            i += 1
            continue
        for pos in range(start, min(i, len(text))):
            if out[pos] not in '\r\n':
                out[pos] = ' '
    return ''.join(out)


def _declarations(source_text):
    masked = _visible_code(source_text)
    stack, starts = [], []
    pairs = {'(': ')', '[': ']', '{': '}'}
    for pos, char in enumerate(masked):
        if char == '#' and not stack and not masked[masked.rfind('\n', 0, pos) + 1:pos].strip():
            starts.append(pos)
        if char in pairs:
            stack.append(pairs[char])
        elif char in ')]}':
            if not stack or stack.pop() != char:
                raise ValueError('Unsupported or unbalanced Typst source')
    if stack:
        raise ValueError('Unsupported or unbalanced Typst source')
    declarations = []
    for pos in starts:
        match = re.match(r'#set\s+text\s*\(', masked[pos:])
        kind = 'body'
        if not match:
            match = re.match(r'#show\s+heading(?:\.where\s*\([^)]*\))?\s*:\s*set\s+text\s*\(', masked[pos:])
            kind = 'heading'
        if not match:
            if re.match(r'#show\s+heading\b', masked[pos:]):
                raise ValueError('Unsupported custom heading declaration; inspect template instead of guessing')
            continue
        opening = pos + match.end() - 1
        depth, end = 1, opening + 1
        while end < len(masked) and depth:
            depth += (masked[end] == '(') - (masked[end] == ')')
            end += 1
        line_end = masked.find('\n', end)
        if masked[end:line_end if line_end >= 0 else len(masked)].strip():
            raise ValueError('Profile declaration must occupy its own line')
        declarations.append((kind, opening, end - 1))
    return declarations


def _replace_arguments(arguments, replacements):
    masked = _visible_code(arguments)
    stack, cuts = [], [0]
    pairs = {'(': ')', '[': ']', '{': '}'}
    for pos, char in enumerate(masked):
        if char in pairs:
            stack.append(pairs[char])
        elif char in ')]}':
            if not stack or stack.pop() != char:
                raise ValueError('Unbalanced declaration arguments')
        elif char == ',' and not stack:
            cuts.append(pos + 1)
    parts = [arguments[a:b - 1] for a, b in zip(cuts, cuts[1:])]
    parts.append(arguments[cuts[-1]:])
    seen = set()
    for index, part in enumerate(parts):
        match = re.match(r'\s*(\w+)\s*:', _visible_code(part))
        if not match or match[1] not in replacements:
            continue
        field = match[1]
        if field in seen:
            raise ValueError('Duplicate ' + field + ' argument')
        seen.add(field)
        value_start = match.end()
        while value_start < len(part) and part[value_start].isspace():
            value_start += 1
        trailing = part[len(part.rstrip()):]
        parts[index] = part[:value_start] + replacements[field] + trailing
    suffix = parts.pop() if parts and not parts[-1].strip() else None
    for field, value in replacements.items():
        if field not in seen:
            parts.append(field + ': ' + value)
    return ','.join(parts) + (',' + suffix if suffix is not None and parts else '')


def apply_profile(source: Path, contract, compiler: Path, font_dir=None, *, env=None):
    validate_contract(contract)
    available = {family.casefold() for family in font_names(compiler, font_dir, env=env)}
    missing = [value for value in contract['fonts'].values() if value.casefold() not in available]
    if missing:
        raise ValueError('Requested fonts unavailable: ' + ', '.join(missing))
    old_bytes = source.read_bytes()
    old = old_bytes.decode('utf-8-sig')
    declarations = _declarations(old)
    bodies = [item for item in declarations if item[0] == 'body']
    if len(bodies) != 1:
        raise ValueError('Need exactly one supported top-level text declaration; inspect custom template instead of guessing')
    fonts = contract['fonts']
    body_font = '(' + json.dumps(fonts['latin'], ensure_ascii=False) + ', ' + json.dumps(fonts['body'], ensure_ascii=False) + ')'
    edits, headings = [], 0
    for kind, opening, closing in declarations:
        replacements = ({'font': body_font, 'size': str(contract['body_size_pt']) + 'pt'}
                        if kind == 'body' else {'font': json.dumps(fonts['heading'], ensure_ascii=False)})
        edits.append((opening + 1, closing, _replace_arguments(old[opening + 1:closing], replacements)))
        headings += kind == 'heading'
    if not headings:
        closing = bodies[0][2]
        newline = '\r\n' if '\r\n' in old else '\n'
        edits.append((closing + 1, closing + 1, newline + '#show heading: set text(font: ' + json.dumps(fonts['heading'], ensure_ascii=False) + ')'))
    source_text = old
    for start, end, replacement in sorted(edits, reverse=True):
        source_text = source_text[:start] + replacement + source_text[end:]
    new_bytes = (b'\xef\xbb\xbf' if old_bytes.startswith(b'\xef\xbb\xbf') else b'') + source_text.encode('utf-8')
    if old_bytes != new_bytes:
        source.write_bytes(new_bytes)
    return {
        'changed': old_bytes != new_bytes,
        'before_sha256': hashlib.sha256(old_bytes).hexdigest(),
        'after_sha256': hashlib.sha256(new_bytes).hexdigest(), 'fonts': fonts,
        'heading_declarations_updated': headings, 'heading_default_added': not headings,
        'scope': 'top-level font/size declarations only; prose, other text settings and model expressions unchanged; margins and rendered roles unverified',
    }


def _font_name_key(value):
    value = re.sub(r'^[A-Z]{6}\+', '', value)
    return ''.join(char for char in value.casefold() if char.isalnum())


def _font_family_matches(family, name):
    expected, actual = _font_name_key(family), _font_name_key(name)
    if actual == expected:
        return True
    styles = {'regular', 'bold', 'italic', 'oblique', 'bolditalic', 'boldoblique',
              'medium', 'mediumitalic', 'semibold', 'semibolditalic', 'light',
              'lightitalic', 'thin', 'thinitalic', 'black', 'blackitalic',
              'extrabold', 'extrabolditalic', 'extralight', 'extralightitalic'}
    if actual.startswith(expected) and actual[len(expected):] in styles:
        return True
    return expected == 'timesnewroman' and actual in {
        'timesnewromanpsmt', 'timesnewromanpsboldmt', 'timesnewromanpsitalicmt',
        'timesnewromanpsbolditalicmt',
    }


def pdf_font_check(pdf: Path, contract):
    validate_contract(contract)
    embedded, resources, used, used_embedded = set(), set(), set(), set()
    checked = {}
    failures = []
    with pymupdf.open(pdf) as doc:
        pages = len(doc)
        for page in doc:
            aliases = {}
            for font in page.get_fonts(full=True):
                resources.add(font[3])
                xref = font[0]
                if xref not in checked:
                    checked[xref] = None
                    try:
                        buffer = doc.extract_font(xref)[-1] if xref else b''
                        if buffer:
                            checked[xref] = pymupdf.Font(fontbuffer=buffer).name
                            embedded.add(checked[xref])
                    except (RuntimeError, ValueError) as exc:
                        failures.append({'font': font[3], 'issue': 'embedded font could not be identified: ' + str(exc)})
                aliases.setdefault(_font_name_key(font[3]), set()).add(checked[xref])
                # Some Type0 resources append the CMap encoding to BaseFont.
                resource_name = re.sub(r'-Identity-[HV]$', '', font[3])
                aliases.setdefault(_font_name_key(resource_name), set()).add(checked[xref])
            text_flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
            for block in page.get_text('dict', flags=text_flags)['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        if span.get('text', '').strip():
                            used.add(span['font'])
                            identities = aliases.get(_font_name_key(span['font']), set())
                            if len(identities) == 1 and None not in identities:
                                used_embedded.update(identities)
                            elif len(identities) > 1:
                                issue = {'font': span['font'], 'issue': 'ambiguous resource-to-text font identity; actual use requires review'}
                                if issue not in failures:
                                    failures.append(issue)
    present = {role: any(_font_family_matches(family, name) for name in embedded) for role, family in contract['fonts'].items()}
    in_text = {role: any(_font_family_matches(family, name) for name in used_embedded) for role, family in contract['fonts'].items()}
    page_minimum = contract.get('minimum_pages') is None or pages >= contract['minimum_pages']
    lightweight = sorted(name for name in embedded | used if re.search(r'(?:thin|(?:extra)?light)(?:italic)?$', name, re.I))
    return {
        'passed': all(present.values()) and all(in_text.values()) and page_minimum,
        'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'pages': pages,
        'minimum_pages_passed': page_minimum,
        'expected_fonts_present': present, 'expected_fonts_used': in_text,
        'embedded_font_names': sorted(embedded), 'resource_font_names': sorted(resources),
        'used_font_names': sorted(used), 'used_embedded_font_names': sorted(used_embedded),
        'font_inspection_issues': failures,
        'lightweight_faces_observed': lightweight,
        'font_style_observation_scope': 'name suffixes only; variable-font PostScript names can differ from embedded metadata and do not prove rendered weight',
        'font_roles_verified': False, 'body_size_verified': False, 'body_font_weight_verified': False,
        'scope': 'actual embedded font identities and family use in extracted text plus chosen page minimum; no proof of paragraph role, glyph correctness, font size/weight, layout or scientific content',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    s = sub.add_parser('svg')
    s.add_argument('asset', type=Path)
    s.add_argument('--engine', default='typst', choices=['typst', 'browser'])
    s = sub.add_parser('fonts')
    s.add_argument('pdf', type=Path)
    s.add_argument('--contract', type=Path, required=True)
    s = sub.add_parser('apply')
    s.add_argument('source', type=Path)
    s.add_argument('--contract', type=Path, required=True)
    s.add_argument('--compiler', type=Path, required=True)
    s.add_argument('--font-dir', type=Path)
    a = p.parse_args()
    if a.action == 'svg':
        result = svg_compatibility(a.asset, a.engine)
    elif a.action == 'fonts':
        result = pdf_font_check(a.pdf, json.loads(a.contract.read_text(encoding='utf-8-sig')))
    else:
        result = apply_profile(a.source, json.loads(a.contract.read_text(encoding='utf-8-sig')), a.compiler, a.font_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('passed', result.get('direct_embedding_ready', True)) is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
