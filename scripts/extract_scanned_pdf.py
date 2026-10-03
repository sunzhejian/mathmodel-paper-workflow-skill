"""Transcribe a PDF's original pages into inspectable, unverified text.

Renderings are PNG copies of source pages, not generated/edited figures. OCR is
optional and lazy. No scientific fields, numbers, table order or formulae are
corrected or certified, and no encrypted file is decrypted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import numbers
from pathlib import Path
import re
import sys

import pymupdf


BACKENDS = {'auto', 'rapidocr', 'legacy', 'none'}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _array(value, label):
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if not isinstance(value, (tuple, list)):
        raise ValueError(label + ' must be a list, tuple or array with matching dimensions')
    return list(value)


def _finite(value, label, *, confidence=False):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(label + ' must be a finite number')
    value = float(value)
    if not math.isfinite(value) or confidence and not 0 <= value <= 1:
        raise ValueError(label + ' must be finite' + (' and between 0 and 1' if confidence else ''))
    return value


def _box(value, label):
    points = _array(value, label)
    if len(points) != 4:
        raise ValueError(label + ' must contain four x/y points')
    result = []
    for index, point in enumerate(points):
        pair = _array(point, f'{label}[{index}]')
        if len(pair) != 2:
            raise ValueError(label + ' must have shape (4, 2)')
        result.append([_finite(pair[0], label + ' x'), _finite(pair[1], label + ' y')])
    return result


def normalize_ocr_result(result):
    """Accept RapidOCROutput attributes or legacy (rows, elapsed), and nothing guessed.

    Legacy rows must each be [quadrilateral, text, confidence]. Modern boxes,
    txts and scores must have exactly matching lengths. Return order is retained.
    """
    if all(hasattr(result, attr) for attr in ('boxes', 'txts', 'scores')):
        boxes, texts, scores = result.boxes, result.txts, result.scores
        result_format = 'rapidocr_attributes'
        if boxes is None and texts is None and scores is None:
            return {'format': result_format, 'blocks': [], 'text': '', 'empty': True}
        boxes = _array(boxes, 'boxes')
        texts = _array(texts, 'txts')
        scores = _array(scores, 'scores')
        if not len(boxes) == len(texts) == len(scores):
            raise ValueError('OCR boxes/txts/scores lengths do not match')
        rows = list(zip(boxes, texts, scores))
    elif isinstance(result, tuple) and len(result) == 2:
        result_format = 'rapidocr_legacy_tuple'
        values = result[0]
        if values is None:
            return {'format': result_format, 'blocks': [], 'text': '', 'empty': True}
        values = _array(values, 'legacy result rows')
        rows = []
        for index, value in enumerate(values):
            row = _array(value, f'legacy result row {index}')
            if len(row) != 3:
                raise ValueError('Legacy OCR row must contain box, text and score')
            rows.append(row)
    else:
        raise ValueError('Unsupported OCR result; expected boxes/txts/scores attributes or legacy (rows, elapsed) tuple')
    blocks = []
    for index, (box, text, score) in enumerate(rows):
        if not isinstance(text, str):
            raise ValueError(f'OCR text at row {index} must be a string')
        blocks.append({'index': index, 'box_pixels': _box(box, f'box {index}'),
                       'text': text, 'score': _finite(score, f'score {index}', confidence=True)})
    # The original backend order/text is not sorted, stripped or made numeric.
    text = '\n'.join(block['text'] for block in blocks)
    return {'format': result_format, 'blocks': blocks, 'text': text, 'empty': not text.strip()}


def parse_pages(value):
    """Parse an explicit one-based selection such as 1,3-5; None means all pages."""
    if value is None or value == 'all':
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Pages must be all or one-based comma-separated pages/ranges')
    pages = []
    for token in value.split(','):
        token = token.strip()
        if re.fullmatch(r'[1-9][0-9]*', token):
            pages.append(int(token))
        elif re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', token):
            start, end = (int(number) for number in token.split('-'))
            if end < start or end - start > 10000:
                raise ValueError('Invalid or excessive page range')
            pages.extend(range(start, end + 1))
        else:
            raise ValueError('Invalid one-based page selection: ' + token)
    if len(set(pages)) != len(pages):
        raise ValueError('Duplicate pages are not allowed')
    return pages


def _version(distribution):
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def _modern_ocr():
    """Bind the installed default ONNX files explicitly; do not trigger downloads.

    RapidOCR 3 exposes default configuration/model metadata used for this
    preflight. A different API or unavailable files produce limited extraction,
    rather than inferring model filenames or installing anything.
    """
    module = importlib.import_module('rapidocr')
    cls = module.RapidOCR
    cfg = cls.__new__(cls)._load_config(None, None)
    model_api = importlib.import_module('rapidocr.inference_engine.base')
    params, model_receipts = {'Global.log_level': 'warning'}, []
    for name in ('Det', 'Cls', 'Rec'):
        section = cfg[name]
        if section.engine_type.value != 'onnxruntime':
            raise RuntimeError('Automatic local preflight currently supports the default ONNX backend only')
        candidate = section.get('model_path')
        if candidate is None:
            info = model_api.InferSession.get_model_url(model_api.FileInfo(
                engine_type=section.engine_type, ocr_version=section.ocr_version,
                task_type=section.task_type, lang_type=section.lang_type,
                model_type=section.model_type))
            candidate = Path(cfg.Global.model_root_dir) / Path(info['model_dir']).name
        candidate = Path(candidate)
        if not candidate.is_file():
            raise FileNotFoundError('Installed OCR model is missing: ' + candidate.name)
        params[name + '.model_path'] = str(candidate)
        model_receipts.append({'role': name, 'file': candidate.name, 'sha256': file_sha256(candidate)})
    # Explicit ONNX models include the recognition character metadata. Never
    # invoke visual overlays, which can need separately downloaded fonts.
    engine = cls(params=params)
    return engine, {'name': 'rapidocr', 'version': _version('rapidocr'),
                    'model_files': model_receipts, 'installation_performed': False,
                    'model_download_requested': False}


def _load_backend(choice):
    failures = []
    names = ['rapidocr', 'legacy'] if choice == 'auto' else [choice]
    for name in names:
        if name == 'none':
            break
        try:
            if name == 'rapidocr':
                return _modern_ocr()
            module = importlib.import_module('rapidocr_onnxruntime')
            # Legacy RapidOCR ships its default models inside its installed
            # package; refuse an installation with missing model files.
            package = Path(module.__file__).resolve().parent
            if len(list((package / 'models').glob('*.onnx'))) < 3:
                raise FileNotFoundError('Legacy OCR package is missing its bundled ONNX models')
            return module.RapidOCR(), {'name': 'rapidocr_onnxruntime',
                                       'version': _version('rapidocr-onnxruntime'),
                                       'installation_performed': False,
                                       'model_download_requested': False}
        except Exception as exc:
            failures.append({'name': name, 'error_type': type(exc).__name__, 'reason': str(exc)})
    return None, {'name': 'unavailable' if choice != 'none' else 'disabled',
                  'attempts': failures, 'installation_performed': False,
                  'model_download_requested': False}


def _positive_int(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + ' must be a positive integer')
    return value


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def extract_pdf(source: Path, output: Path, *, pages=None, dpi=180, backend='auto',
                min_native_chars=40, max_total_pixels=400_000_000,
                max_page_pixels=40_000_000, ocr_callable=None, progress=None):
    """Copy selected source pages and full native/OCR text to a NEW output directory.

    An extraction_complete receipt does not validate reading order, symbols,
    numerals, table structure, evidence quality or any scientific conclusion.
    """
    source, output = Path(source).resolve(strict=True), Path(output)
    if not source.is_file():
        raise ValueError('Source must be an existing PDF file')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Output must be a new directory; existing files are never overwritten')
    _positive_int(dpi, 'dpi')
    if not 72 <= dpi <= 400:
        raise ValueError('dpi must be between 72 and 400')
    _positive_int(min_native_chars, 'min_native_chars')
    _positive_int(max_total_pixels, 'max_total_pixels')
    _positive_int(max_page_pixels, 'max_page_pixels')
    if backend not in BACKENDS:
        raise ValueError('Unsupported OCR backend')
    if ocr_callable is not None and not callable(ocr_callable):
        raise ValueError('ocr_callable must be callable')
    before = file_sha256(source)
    with pymupdf.open(source) as doc:
        if doc.needs_pass or doc.is_encrypted:
            raise ValueError('Encrypted PDFs are unsupported; provide an accessible original')
        selected = list(range(1, len(doc) + 1)) if pages is None else list(pages)
        if (not selected or len(set(selected)) != len(selected)
                or any(type(page) is not int or not 1 <= page <= len(doc) for page in selected)):
            raise ValueError('pages must select distinct existing one-based PDF pages')
        planned = []
        for page_number in selected:
            rect = doc[page_number - 1].rect
            width, height = math.ceil(rect.width * dpi / 72), math.ceil(rect.height * dpi / 72)
            pixels = width * height
            if pixels > max_page_pixels:
                raise ValueError(f'Page {page_number} exceeds the declared per-page pixel budget')
            planned.append(pixels)
        if sum(planned) > max_total_pixels:
            raise ValueError('Selected pages exceed the declared total pixel budget; select pages or explicitly raise the budget')
        # mkdir is exclusive even if another process races after the exists check.
        output.mkdir(parents=True, exist_ok=False)
        report = {'schema_version': 1, 'source': str(source), 'source_sha256_before': before,
                  'source_sha256_after': None, 'original_unmodified': None,
                  'total_source_pages': len(doc), 'selected_pages': selected,
                  'dpi': dpi, 'pixel_budget': {'per_page': max_page_pixels, 'total': max_total_pixels},
                  'min_native_chars': min_native_chars, 'native_adequacy_rule': 'count of non-whitespace characters; heuristic only, not full-page coverage proof',
                  'backend': {'name': 'not_needed'}, 'pages': [], 'status': 'in_progress',
                  'extraction_complete': False, 'scientific_verified': False,
                  'numeric_values_verified': False, 'reading_order_verified': False,
                  'formula_transcription_verified': False,
                  'scope': 'Original-page rendering and unverified transcription only. No field selection, table reconstruction, unit conversion, number correction, scientific matrix generation or solution.',
                  'limitations': ['OCR/native text may misread symbols, table order, decimal marks and numeric values; compare with the retained source page.'],
                  'manifest': str(output / 'manifest.json')}
        engine, initialized = ocr_callable, ocr_callable is not None
        if engine is not None:
            report['backend'] = {'name': 'injected_callable', 'installation_performed': False}
        total_pixels = 0
        for page_number in selected:
            page = doc[page_number - 1]
            stem = f'page-{page_number:04d}'
            image_path = output / (stem + '.png')
            native_path = output / (stem + '.native.txt')
            text_path = output / (stem + '.txt')
            ocr_path = output / (stem + '.ocr.json')
            entry = {'page': page_number, 'image': image_path.name, 'native_text': native_path.name,
                     'text': text_path.name, 'ocr': ocr_path.name, 'status': 'failed',
                     'transcription_verified': False, 'reading_order_verified': False,
                     'numeric_values_verified': False}
            try:
                pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
                pixels = pixmap.width * pixmap.height
                total_pixels += pixels
                if pixels > max_page_pixels or total_pixels > max_total_pixels:
                    raise ValueError('Actual rendered pixels exceed the declared pixel budget')
                pixmap.save(image_path)
                entry.update(width_px=pixmap.width, height_px=pixmap.height,
                             image_sha256=file_sha256(image_path))
                native = page.get_text('text', sort=False)
                native_path.write_text(native, encoding='utf-8')
                chars = len(re.sub(r'\s', '', native))
                entry.update(native_character_count=chars, native_text_sha256=file_sha256(native_path))
                ocr_report = {'page': page_number, 'boxes_coordinate_system': 'pixels of retained page PNG',
                              'ordering': 'backend return order retained; scientific/table reading order not validated',
                              'transcription_verified': False, 'blocks': []}
                if chars >= min_native_chars:
                    text = native
                    entry['status'] = 'native_text_extracted'
                    ocr_report.update(status='not_needed_by_native_text_heuristic')
                else:
                    if not initialized:
                        engine, backend_receipt = _load_backend(backend)
                        report['backend'] = backend_receipt
                        initialized = True
                    if engine is None:
                        text = native
                        entry['status'] = 'limited_backend_unavailable'
                        ocr_report.update(status=entry['status'])
                    else:
                        normalized = normalize_ocr_result(engine(str(image_path)))
                        ocr_report.update(format=normalized['format'], blocks=normalized['blocks'])
                        if normalized['empty']:
                            text = native
                            entry['status'] = 'limited_empty_ocr'
                        else:
                            text = normalized['text']
                            entry['status'] = 'ocr_transcribed_unverified'
                        ocr_report.update(status=entry['status'])
                text_path.write_text(text, encoding='utf-8')
                _write_json(ocr_path, ocr_report)
                entry.update(text_sha256=file_sha256(text_path), ocr_sha256=file_sha256(ocr_path))
            except Exception as exc:
                entry.update(status='failed', error_type=type(exc).__name__, error=str(exc))
                # Invalid backend payloads are rejected, not silently converted
                # to empty success or scientific tables.
                _write_json(ocr_path, {'page': page_number, 'status': 'failed',
                                       'error_type': type(exc).__name__, 'error': str(exc),
                                       'transcription_verified': False, 'blocks': []})
            report['pages'].append(entry)
            _write_json(output / 'manifest.json', report)
            if progress:
                progress({'page': page_number, 'completed': len(report['pages']),
                          'selected': len(selected), 'status': entry['status']})
        after = file_sha256(source)
        report.update(source_sha256_after=after, original_unmodified=before == after,
                      rendered_total_pixels=total_pixels)
        if before != after or any(page['status'] == 'failed' for page in report['pages']):
            report['status'] = 'failed'
        elif any(page['status'].startswith('limited_') for page in report['pages']):
            report['status'] = 'limited'
        else:
            report.update(status='extracted_unverified', extraction_complete=True)
        _write_json(output / 'manifest.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pages', help='all (default), or one-based pages/ranges, e.g. 1,3-5')
    parser.add_argument('--dpi', type=int, default=180)
    parser.add_argument('--backend', choices=sorted(BACKENDS), default='auto')
    parser.add_argument('--min-native-chars', type=int, default=40)
    parser.add_argument('--max-total-pixels', type=int, default=400_000_000)
    parser.add_argument('--max-page-pixels', type=int, default=40_000_000)
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    def progress(value):
        print(json.dumps(value, ensure_ascii=False), file=sys.stderr, flush=True)
    try:
        report = extract_pdf(args.source, args.output, pages=parse_pages(args.pages), dpi=args.dpi,
                             backend=args.backend, min_native_chars=args.min_native_chars,
                             max_total_pixels=args.max_total_pixels, max_page_pixels=args.max_page_pixels,
                             progress=None if args.quiet else progress)
    except (ValueError, OSError, pymupdf.FileDataError) as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}))
        return 1
    print(json.dumps({key: report[key] for key in ('status', 'extraction_complete', 'scientific_verified',
                                                  'manifest', 'selected_pages', 'source_sha256_before',
                                                  'source_sha256_after', 'original_unmodified')}, ensure_ascii=False))
    return 0 if report['status'] == 'extracted_unverified' else 2 if report['status'] == 'limited' else 1


if __name__ == '__main__':
    raise SystemExit(main())
