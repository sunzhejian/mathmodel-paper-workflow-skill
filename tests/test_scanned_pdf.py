from dataclasses import dataclass
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('scanned_pdf_test', ROOT / 'scripts/extract_scanned_pdf.py')
EXTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACT)

BOX = [[5, 10], [150, 10], [150, 30], [5, 30]]


@dataclass
class Output:
    boxes: object = None
    txts: object = None
    scores: object = None


class ArrayLike:
    def __init__(self, value):
        self.value = value

    def tolist(self):
        return self.value


def make_pdf(path, *, texts=None, raster=False, pages=1):
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page(width=300, height=400)
        if raster:
            with pymupdf.open() as image_source:
                original = image_source.new_page(width=300, height=400)
                original.insert_text((20, 40), 'Synthetic scanned input 0.1500', fontsize=12)
                png = original.get_pixmap(dpi=100).tobytes('png')
            page.insert_image(page.rect, stream=png)
        elif texts:
            page.insert_textbox(pymupdf.Rect(20, 30, 270, 350), texts[index], fontsize=12)
    doc.save(path)
    doc.close()


class ScannedPdfTests(unittest.TestCase):
    def test_modern_attributes_preserve_text_order_boxes_and_scores(self):
        value = EXTRACT.normalize_ocr_result(Output([BOX, BOX], ('second 0.1500', ' first 1.00 '), (.95, .8)))
        self.assertEqual(value['format'], 'rapidocr_attributes')
        self.assertEqual(value['text'], 'second 0.1500\n first 1.00 ')
        self.assertEqual([row['index'] for row in value['blocks']], [0, 1])
        self.assertEqual(value['blocks'][0]['box_pixels'], BOX)
        self.assertEqual(value['blocks'][1]['score'], .8)
        self.assertFalse(value['empty'])

    def test_array_like_modern_boxes_are_supported_without_numpy_dependency(self):
        value = EXTRACT.normalize_ocr_result(Output(ArrayLike([BOX]), ArrayLike(['text']), ArrayLike([.9])))
        self.assertEqual(value['blocks'][0]['text'], 'text')

    def test_legacy_tuple_rows_are_supported(self):
        value = EXTRACT.normalize_ocr_result(([[BOX, '0.001 is lexical text', .75]], [.1, .2, .3]))
        self.assertEqual(value['format'], 'rapidocr_legacy_tuple')
        self.assertEqual(value['text'], '0.001 is lexical text')

    def test_empty_modern_and_legacy_payloads_are_empty_not_success(self):
        for result in (Output(), Output([], (), []), (None, None), ([], [.1])):
            with self.subTest(result=result):
                self.assertTrue(EXTRACT.normalize_ocr_result(result)['empty'])

    def test_only_whitespace_text_is_not_success(self):
        value = EXTRACT.normalize_ocr_result(Output([BOX], [' \n '], [.99]))
        self.assertTrue(value['empty'])
        self.assertEqual(value['blocks'][0]['text'], ' \n ')

    def test_mismatched_modern_lengths_are_rejected(self):
        for value in (Output([BOX], [], [.9]), Output([], ['one'], []), Output([BOX], ['one'], [.9, .8])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EXTRACT.normalize_ocr_result(value)

    def test_partial_none_is_rejected(self):
        with self.assertRaises(ValueError):
            EXTRACT.normalize_ocr_result(Output([BOX], ['one'], None))

    def test_unrecognized_tuple_and_dict_are_not_guessed(self):
        for result in ((), ([BOX], ['one'], [.9]), [None, None], {'boxes': [], 'txts': [], 'scores': []}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                EXTRACT.normalize_ocr_result(result)

    def test_legacy_row_shape_is_validated(self):
        for rows in ([[BOX, 'x']], [[BOX, 'x', .9, 'extra']], [[BOX, ('x', .9)]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                EXTRACT.normalize_ocr_result((rows, None))

    def test_quadrilateral_shape_and_finite_coordinates_are_validated(self):
        for box in ([[1, 2]], [[1, 2, 3]] * 4, [[math.nan, 2]] * 4, [[True, 2]] * 4,
                    [['1', 2]] * 4, [1, 2, 3, 4]):
            with self.subTest(box=box), self.assertRaises(ValueError):
                EXTRACT.normalize_ocr_result(Output([box], ['x'], [.9]))

    def test_confidence_must_be_numeric_finite_and_in_range(self):
        for score in (math.nan, math.inf, -math.inf, '0.9', True, -.1, 1.1):
            with self.subTest(score=score), self.assertRaises(ValueError):
                EXTRACT.normalize_ocr_result(Output([BOX], ['x'], [score]))

    def test_text_must_remain_a_string(self):
        with self.assertRaises(ValueError):
            EXTRACT.normalize_ocr_result(Output([BOX], [150], [.9]))

    def test_explicit_pages_parse_with_ranges(self):
        self.assertIsNone(EXTRACT.parse_pages(None))
        self.assertIsNone(EXTRACT.parse_pages('all'))
        self.assertEqual(EXTRACT.parse_pages('3, 1-2'), [3, 1, 2])

    def test_invalid_and_duplicate_page_text_is_rejected(self):
        for value in ('', '0', '-1', '1,', '1,1', '1-2,2', '5-2', '1.2', 'one', '1-20000'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EXTRACT.parse_pages(value)

    def test_native_text_is_reused_without_loading_optional_backend(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'original.pdf'
            make_pdf(source, texts=['A genuine native-text PDF with enough complete text to avoid any OCR call.'])
            before = source.read_bytes()
            with mock.patch.object(EXTRACT, '_load_backend', side_effect=AssertionError('must not load')):
                report = EXTRACT.extract_pdf(source, Path(folder) / 'new', backend='auto')
            self.assertEqual(report['status'], 'extracted_unverified')
            self.assertTrue(report['extraction_complete'])
            self.assertFalse(report['scientific_verified'])
            self.assertEqual(report['backend']['name'], 'not_needed')
            self.assertEqual(report['pages'][0]['status'], 'native_text_extracted')
            self.assertEqual(before, source.read_bytes())
            self.assertTrue(report['original_unmodified'])

    def test_real_raster_page_is_rendered_to_png_and_mock_ocr_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'original.pdf', Path(folder) / 'new'
            make_pdf(source, raster=True)
            before = EXTRACT.file_sha256(source)
            calls = []
            def backend(path):
                self.assertEqual(Path(path).read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
                calls.append(path)
                return Output([BOX, BOX], ['0.1500', 'table order uncertain'], [.8, .9])
            report = EXTRACT.extract_pdf(source, output, ocr_callable=backend)
            self.assertEqual(report['status'], 'extracted_unverified')
            self.assertEqual(len(calls), 1)
            self.assertEqual(report['pages'][0]['native_character_count'], 0)
            self.assertEqual((output / 'page-0001.txt').read_text(), '0.1500\ntable order uncertain')
            ledger = json.loads((output / 'page-0001.ocr.json').read_text())
            self.assertEqual(ledger['blocks'][0]['text'], '0.1500')
            self.assertFalse(ledger['transcription_verified'])
            self.assertFalse(report['numeric_values_verified'])
            self.assertFalse(report['reading_order_verified'])
            self.assertEqual(report['source_sha256_before'], before)
            self.assertEqual(report['source_sha256_after'], before)

    def test_blank_page_empty_ocr_is_limited(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'blank.pdf'
            make_pdf(source)
            report = EXTRACT.extract_pdf(source, Path(folder) / 'new', ocr_callable=lambda image: Output())
            self.assertEqual(report['status'], 'limited')
            self.assertFalse(report['extraction_complete'])
            self.assertEqual(report['pages'][0]['status'], 'limited_empty_ocr')

    def test_missing_backend_preserves_png_native_and_limited_state(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'short.pdf', Path(folder) / 'new'
            make_pdf(source, texts=['A'])
            with mock.patch.object(EXTRACT, '_load_backend', return_value=(None, {'name': 'unavailable'})):
                report = EXTRACT.extract_pdf(source, output)
            self.assertEqual(report['status'], 'limited')
            self.assertTrue((output / 'page-0001.png').is_file())
            self.assertEqual((output / 'page-0001.txt').read_text(), (output / 'page-0001.native.txt').read_text())
            self.assertFalse(report['extraction_complete'])

    def test_invalid_backend_payload_marks_page_failure_with_no_claimed_success(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'scan.pdf', Path(folder) / 'new'
            make_pdf(source, raster=True)
            report = EXTRACT.extract_pdf(source, output, ocr_callable=lambda image: Output([BOX], ['x'], [math.inf]))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['pages'][0]['error_type'], 'ValueError')
            self.assertFalse(report['extraction_complete'])
            ledger = json.loads((output / 'page-0001.ocr.json').read_text())
            self.assertEqual(ledger['status'], 'failed')

    def test_source_change_during_backend_call_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'scan.pdf'
            make_pdf(source, raster=True)
            def changing_backend(image):
                with source.open('ab') as handle:
                    handle.write(b'\n% intentional test alteration\n')
                return Output([BOX], ['x'], [.8])
            report = EXTRACT.extract_pdf(source, Path(folder) / 'new', ocr_callable=changing_backend)
            self.assertEqual(report['status'], 'failed')
            self.assertFalse(report['original_unmodified'])
            self.assertNotEqual(report['source_sha256_before'], report['source_sha256_after'])

    def test_explicit_page_selection_retains_original_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'scan.pdf', Path(folder) / 'new'
            make_pdf(source, raster=True, pages=3)
            report = EXTRACT.extract_pdf(source, output, pages=[3, 1], ocr_callable=lambda image: ([ [BOX, 'x', .9] ], None))
            self.assertEqual(report['selected_pages'], [3, 1])
            self.assertEqual([page['page'] for page in report['pages']], [3, 1])
            self.assertFalse((output / 'page-0002.png').exists())
            self.assertTrue((output / 'page-0003.png').exists())

    def test_all_pages_are_default_and_backend_load_happens_once(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'scan.pdf'
            make_pdf(source, raster=True, pages=2)
            engine = mock.Mock(return_value=Output([BOX], ['x'], [.9]))
            with mock.patch.object(EXTRACT, '_load_backend', return_value=(engine, {'name': 'mock'})) as load:
                report = EXTRACT.extract_pdf(source, Path(folder) / 'new')
            self.assertEqual(report['selected_pages'], [1, 2])
            load.assert_called_once_with('auto')
            self.assertEqual(engine.call_count, 2)

    def test_existing_directory_and_source_path_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.pdf', Path(folder) / 'existing'
            make_pdf(source)
            before = source.read_bytes()
            output.mkdir()
            marker = output / 'keep.txt'
            marker.write_text('keep')
            for destination in (source, output):
                with self.subTest(destination=destination), self.assertRaises(FileExistsError):
                    EXTRACT.extract_pdf(source, destination)
            self.assertEqual(before, source.read_bytes())
            self.assertEqual(marker.read_text(), 'keep')

    def test_invalid_api_page_selection_rejected_before_output_created(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.pdf'
            make_pdf(source)
            for pages in ([], [0], [True], [2], [1, 1]):
                output = Path(folder) / 'new'
                with self.subTest(pages=pages), self.assertRaises(ValueError):
                    EXTRACT.extract_pdf(source, output, pages=pages)
                self.assertFalse(output.exists())

    def test_dpi_and_pixel_budget_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.pdf'
            make_pdf(source, pages=2)
            for options in ({'dpi': True}, {'dpi': 50}, {'dpi': 500}, {'max_total_pixels': 1},
                            {'max_page_pixels': 1}, {'min_native_chars': 0}, {'backend': 'unknown'}):
                output = Path(folder) / 'new'
                with self.subTest(options=options), self.assertRaises(ValueError):
                    EXTRACT.extract_pdf(source, output, **options)
                self.assertFalse(output.exists())

    def test_encrypted_pdf_is_rejected_without_decryption_or_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'locked.pdf', Path(folder) / 'new'
            with pymupdf.open() as doc:
                doc.new_page()
                doc.save(source, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='user')
            before = source.read_bytes()
            with self.assertRaises(ValueError):
                EXTRACT.extract_pdf(source, output)
            self.assertEqual(before, source.read_bytes())
            self.assertFalse(output.exists())

    def test_disabled_backend_never_imports_optional_ocr(self):
        with mock.patch.object(EXTRACT.importlib, 'import_module', side_effect=AssertionError('must not import')):
            engine, receipt = EXTRACT._load_backend('none')
        self.assertIsNone(engine)
        self.assertEqual(receipt['name'], 'disabled')

    def test_unavailable_import_is_limited_not_install_attempt(self):
        with mock.patch.object(EXTRACT.importlib, 'import_module', side_effect=ModuleNotFoundError('optional missing')):
            engine, receipt = EXTRACT._load_backend('auto')
        self.assertIsNone(engine)
        self.assertEqual(len(receipt['attempts']), 2)
        self.assertFalse(receipt['installation_performed'])
        self.assertFalse(receipt['model_download_requested'])

    def test_cli_disabled_ocr_returns_limited_with_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'scan.pdf', Path(folder) / 'new'
            make_pdf(source, raster=True)
            result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/extract_scanned_pdf.py'),
                                     str(source), '--output', str(output), '--backend', 'none', '--quiet'],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'limited')
            self.assertTrue((output / 'manifest.json').is_file())

    def test_cli_native_text_succeeds_without_ocr_and_source_hash_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'native.pdf', Path(folder) / 'new'
            make_pdf(source, texts=['The full native source content is retained and requires no optional OCR backend.'])
            result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/extract_scanned_pdf.py'),
                                     str(source), '--output', str(output), '--quiet'],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt['original_unmodified'])
            self.assertEqual(receipt['source_sha256_before'], receipt['source_sha256_after'])


if __name__ == '__main__':
    unittest.main()
