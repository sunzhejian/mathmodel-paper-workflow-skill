"""Configurable PDF checks and appendix preservation. Page numbers are one-based."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import fitz
import numpy as np
from PIL import Image, ImageDraw


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_report(path, data, protected=()):
    target = Path(path).resolve()
    if target in {Path(p).resolve() for p in protected}:
        raise ValueError('Report path must differ from input/output PDFs')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def blank_metrics(page, margins_cm, dpi=108):
    top, right, bottom, left = [v * 72 / 2.54 for v in margins_cm]
    rect = page.rect
    clip = fitz.Rect(rect.x0+left, rect.y0+top, rect.x1-right, rect.y1-bottom)
    if min(margins_cm) < 0 or clip.width < 10 or clip.height < 10:
        raise ValueError('Margins leave an invalid content rectangle')
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = (arr < 220).sum(axis=1) > 2
    occupied = np.flatnonzero(ink)
    tail_rows = len(ink) if not len(occupied) else len(ink)-1-int(occupied[-1])
    runs, start = [], None
    for i, present in enumerate(ink):
        if not present and start is None:
            start = i
        if present and start is not None:
            runs.append(i-start)
            start = None
    if start is not None:
        runs.append(len(ink)-start)
    return {
        'tail_blank_percent': 100 * tail_rows / len(ink),
        'max_vertical_blank_percent': 100 * max(runs, default=0) / len(ink),
        'empty_content_region': not bool(len(occupied)),
    }


def render_pages(doc, indices, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for i in indices:
        pix = doc[i].get_pixmap(dpi=120, alpha=False)
        pix.save(directory / f'page_{i+1:03d}.png')
        thumb = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        thumb.thumbnail((400, 566))
        frame = Image.new('RGB', (410, 596), '#dddddd')
        frame.paste(thumb, ((410-thumb.width)//2, 25))
        ImageDraw.Draw(frame).text((10, 7), f'Page {i+1}', fill='black')
        thumbs.append(frame)
    for first in range(0, len(thumbs), 6):
        group = thumbs[first:first+6]
        sheet = Image.new('RGB', (1230, 596*((len(group)+2)//3)), '#aaaaaa')
        for j, im in enumerate(group):
            sheet.paste(im, ((j%3)*410, (j//3)*596))
        sheet.save(directory / f'contact_{indices[first]+1:03d}.png')


def audit(args):
    if args.blank_limit is not None and not 0 <= args.blank_limit <= 100:
        raise ValueError('blank-limit must be between 0 and 100')
    if args.exact_pages is not None and args.max_pages is not None:
        raise ValueError('Choose exact-pages or max-pages, not both')
    if Path(args.report).resolve() == Path(args.pdf).resolve():
        raise ValueError('Report must not overwrite the PDF')
    with fitz.open(args.pdf) as doc:
        last = args.last_page if args.last_page is not None else len(doc)
        if not 1 <= args.first_page <= last <= len(doc):
            raise ValueError('Invalid selected page range')
        indices = list(range(args.first_page-1, last))
        failures, records = [], []
        if args.max_pages is not None and len(indices) > args.max_pages:
            failures.append('Selected page count exceeds maximum')
        if args.exact_pages is not None and len(indices) != args.exact_pages:
            failures.append('Selected page count differs from exact requirement')
        for i in indices:
            page = doc[i]
            metrics = blank_metrics(page, args.margins_cm)
            raw = re.findall(r'\\(?:frac|begin|end|partial|mathrm|label|ref|boxed)\b|\?\?|\$|\^\{|_\{', page.get_text())
            record = {'page': i+1, **metrics, 'suspected_raw_formula_tokens': sorted(set(raw))}
            records.append(record)
            if args.blank_limit is not None and metrics['max_vertical_blank_percent'] > args.blank_limit:
                failures.append(f'Page {i+1}: continuous blank band exceeds limit')
            if raw:
                failures.append(f'Page {i+1}: suspected formula text requires visual review')
        if args.render_dir:
            render_pages(doc, indices, args.render_dir)
        report = {'pdf_sha256': sha256(args.pdf), 'total_pages': len(doc),
                  'selected_pages': len(indices), 'margins_cm_top_right_bottom_left': args.margins_cm,
                  'blank_limit_percent': args.blank_limit,
                  'measurement': 'Full-width continuous blank height / content-region height; excludes margins; NOT total white-pixel area or overlap detection',
                  'pages': records, 'failures': failures, 'passed': not failures}
        write_report(args.report, report, [args.pdf])
        print(json.dumps({'pages_checked': len(indices), 'max_blank_percent': round(max(r['max_vertical_blank_percent'] for r in records), 2), 'failures': failures}, ensure_ascii=False))
        return 1 if failures else 0


def empty_footer(page, footer):
    if page.get_text(clip=footer).strip():
        return False
    pix = page.get_pixmap(dpi=144, clip=footer, colorspace=fitz.csGRAY, alpha=False)
    return not any(value < 245 for value in pix.samples)


def compare_page_content(old, new, clip):
    if old.rect != new.rect:
        raise ValueError('Appendix page dimensions changed')
    a = old.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), clip=clip, alpha=False)
    b = new.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), clip=clip, alpha=False)
    if a.samples != b.samples or old.get_text(clip=clip) != new.get_text(clip=clip):
        raise ValueError('Appendix content verification failed')


def append(args):
    output = Path(args.output).resolve()
    inputs = [Path(args.body).resolve(), Path(args.original).resolve()]
    report_path = Path(args.report).resolve()
    if output in inputs or output.exists() or report_path in inputs+[output]:
        raise ValueError('Use new output PDF and distinct report paths')
    if args.font_size <= 0 or args.footer_height_pt <= 0:
        raise ValueError('Invalid footer dimensions')
    if args.number_pages and not 6 <= args.footer_baseline_from_bottom_pt <= args.footer_height_pt-args.font_size:
        raise ValueError('Page-number baseline/font must fit inside footer band')
    with fitz.open(args.body) as body, fitz.open(args.original) as source, fitz.open() as out:
        if not 1 <= args.appendix_start <= len(source):
            raise ValueError('appendix-start is outside source PDF')
        first = args.appendix_start-1
        page_start = args.start_number if args.start_number is not None else len(body)+1
        if page_start < 1:
            raise ValueError('Start number must be positive')
        out.insert_pdf(body)
        out.insert_pdf(source, from_page=first)
        for j in range(len(source)-first):
            page = out[len(body)+j]
            if page.rotation:
                raise ValueError('Rotated appendix pages require separate handling')
            if not args.number_pages:
                continue
            if args.footer_height_pt >= page.rect.height:
                raise ValueError('Footer band must be smaller than page')
            footer = fitz.Rect(0, page.rect.height-args.footer_height_pt, page.rect.width, page.rect.height)
            if not empty_footer(page, footer):
                raise ValueError(f'Original appendix page {first+j+1} has occupied footer; nothing overwritten')
            number = str(page_start+j)
            width = fitz.get_text_length(number, fontname='tiro', fontsize=args.font_size)
            if width > page.rect.width-20:
                raise ValueError('Page number too wide')
            page.insert_text(((page.rect.width-width)/2, page.rect.height-args.footer_baseline_from_bottom_pt), number, fontname='tiro', fontsize=args.font_size, color=(0, 0, 0))
        blob = out.tobytes(garbage=4, deflate=True)
        with fitz.open(stream=blob, filetype='pdf') as final:
            for j in range(len(source)-first):
                old, new = source[first+j], final[len(body)+j]
                clip = fitz.Rect(old.rect)
                if args.number_pages:
                    clip.y1 -= args.footer_height_pt
                    footer = fitz.Rect(0, clip.y1, old.rect.width, old.rect.height)
                    if new.get_text(clip=footer).strip() != str(page_start+j):
                        raise ValueError('Added footer number did not verify')
                compare_page_content(old, new, clip)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(blob)
        report = {'body_pages': len(body), 'appendix_pages': len(source)-first,
                  'total_pages': len(out), 'appendix_pages_verified': len(source)-first,
                  'numbered_appendix': args.number_pages,
                  'appendix_number_range': [page_start, page_start+len(source)-first-1] if args.number_pages else None,
                  'body_sha256': sha256(args.body), 'source_sha256': sha256(args.original),
                  'output_sha256': sha256(output),
                  'preservation_scope': 'Rendered pixels and extracted page text; excludes added footer band when numbering; not PDF signatures or document-level metadata'}
        write_report(args.report, report, inputs+[output])
        print(json.dumps(report, ensure_ascii=False))
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('audit')
    a.add_argument('pdf')
    a.add_argument('--first-page', type=int, default=1)
    a.add_argument('--last-page', type=int)
    a.add_argument('--max-pages', type=int)
    a.add_argument('--exact-pages', type=int)
    a.add_argument('--margins-cm', type=float, nargs=4, default=[2.5]*4, metavar=('TOP', 'RIGHT', 'BOTTOM', 'LEFT'))
    a.add_argument('--blank-limit', type=float)
    a.add_argument('--report', required=True)
    a.add_argument('--render-dir')
    a.set_defaults(run=audit)
    p = sub.add_parser('append')
    p.add_argument('body'); p.add_argument('original'); p.add_argument('output')
    p.add_argument('--appendix-start', type=int, required=True)
    p.add_argument('--number-pages', action='store_true')
    p.add_argument('--start-number', type=int)
    p.add_argument('--font-size', type=float, default=12)
    p.add_argument('--footer-height-pt', type=float, default=42)
    p.add_argument('--footer-baseline-from-bottom-pt', type=float, default=25)
    p.add_argument('--report', required=True)
    p.set_defaults(run=append)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
