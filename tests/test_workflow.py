import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import fitz

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


pdf = module('pdf_workflow')
package = module('package_support')


class WorkflowTests(unittest.TestCase):
    def test_portable_utf8_text_resources(self):
        candidates = list(ROOT.glob('*.md'))
        for directory in ['agents', 'references', 'scripts', 'tests', '.github']:
            candidates.extend(p for p in (ROOT/directory).rglob('*') if p.suffix in {'.md', '.py', '.yml', '.yaml'})
        for path in candidates:
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_bytes().decode('utf-8')
                self.assertNotIn('\ufffd', text)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_pdf(self, name, count=1, filled=True, footer=False, raw=False, rotated=False):
        path = self.root/name
        with fitz.open() as doc:
            for i in range(count):
                page = doc.new_page(width=595, height=842)
                if filled:
                    for y in range(90, 752, 20):
                        page.insert_text((75, y), f'Synthetic page {i+1} at y={y}: model evidence', fontsize=11)
                if footer:
                    # A vector mark, not extractable text, must also block numbering.
                    page.draw_rect(fitz.Rect(250, 817, 330, 820), color=(0, 0, 0), fill=(0, 0, 0))
                if raw:
                    page.insert_text((75, 765), r'\frac{x}{y}')
                if rotated:
                    page.set_rotation(90)
            doc.save(path)
        return path

    def append_args(self, original, numbering=True):
        return argparse.Namespace(body=self.make_pdf('body.pdf'), original=original,
                                  output=self.root/'final.pdf', appendix_start=1,
                                  report=self.root/'append.json', number_pages=numbering,
                                  start_number=None, font_size=12, footer_height_pt=42,
                                  footer_baseline_from_bottom_pt=25)

    def test_empty_page_reports_100_percent(self):
        p = self.make_pdf('blank.pdf', filled=False)
        with fitz.open(p) as doc:
            metrics = pdf.blank_metrics(doc[0], [2.5]*4)
            self.assertEqual(metrics['tail_blank_percent'], 100)
            self.assertTrue(metrics['empty_content_region'])

    def test_filled_page_under_limit(self):
        with fitz.open(self.make_pdf('filled.pdf')) as doc:
            self.assertLess(pdf.blank_metrics(doc[0], [2.5]*4)['max_vertical_blank_percent'], 20)

    def test_invalid_margins(self):
        with fitz.open(self.make_pdf('filled.pdf')) as doc:
            with self.assertRaises(ValueError):
                pdf.blank_metrics(doc[0], [25]*4)

    def test_append_preserves_content_and_numbers(self):
        source = self.make_pdf('original.pdf', count=2)
        before = source.read_bytes()
        args = self.append_args(source)
        self.assertEqual(pdf.append(args), 0)
        self.assertEqual(source.read_bytes(), before)
        with fitz.open(source) as old, fitz.open(args.output) as new:
            self.assertEqual(len(new), 3)
            clip = fitz.Rect(0, 0, 595, 800)
            for i in range(2):
                pdf.compare_page_content(old[i], new[i+1], clip)
                self.assertEqual(new[i+1].get_text(clip=fitz.Rect(0, 800, 595, 842)).strip(), str(i+2))

    def test_append_without_numbering_preserves_full_page(self):
        source = self.make_pdf('original.pdf', footer=True)
        args = self.append_args(source, numbering=False)
        pdf.append(args)
        with fitz.open(source) as old, fitz.open(args.output) as new:
            pdf.compare_page_content(old[0], new[1], old[0].rect)

    def test_occupied_vector_footer_blocks_numbering(self):
        args = self.append_args(self.make_pdf('original.pdf', footer=True))
        with self.assertRaisesRegex(ValueError, 'occupied footer'):
            pdf.append(args)
        self.assertFalse(Path(args.output).exists())

    def test_existing_output_not_overwritten(self):
        args = self.append_args(self.make_pdf('original.pdf'))
        Path(args.output).write_bytes(b'keep')
        with self.assertRaises(ValueError):
            pdf.append(args)
        self.assertEqual(Path(args.output).read_bytes(), b'keep')

    def test_rotated_appendix_rejected(self):
        args = self.append_args(self.make_pdf('original.pdf', rotated=True))
        with self.assertRaisesRegex(ValueError, 'Rotated'):
            pdf.append(args)

    def test_selected_range_ignores_appendix_and_renders(self):
        source = self.make_pdf('paper.pdf')
        with fitz.open(source) as doc:
            doc.new_page()
            doc.save(self.root/'combined.pdf')
        args = ['audit', str(self.root/'combined.pdf'), '--last-page', '1', '--exact-pages', '1', '--blank-limit', '20', '--report', str(self.root/'qa.json'), '--render-dir', str(self.root/'render')]
        self.assertEqual(pdf.main(args), 0)
        self.assertTrue((self.root/'render/page_001.png').exists())
        self.assertFalse((self.root/'render/page_002.png').exists())

    def test_raw_formula_is_flagged(self):
        source = self.make_pdf('raw.pdf', raw=True)
        self.assertEqual(pdf.main(['audit', str(source), '--report', str(self.root/'qa.json')]), 1)

    def test_blank_limit_failure(self):
        source = self.make_pdf('blank.pdf', filled=False)
        self.assertEqual(pdf.main(['audit', str(source), '--blank-limit', '20', '--report', str(self.root/'qa.json')]), 1)

    def test_invalid_range_fails(self):
        source = self.make_pdf('one.pdf')
        self.assertEqual(pdf.main(['audit', str(source), '--last-page', '2', '--report', str(self.root/'qa.json')]), 2)

    def allowlist(self, items):
        path = self.root/'files.json'
        path.write_text(json.dumps(items), encoding='utf-8')
        return path

    def test_package_round_trip(self):
        (self.root/'result.csv').write_text('t,c\n1,0.123456789\n', encoding='utf-8')
        listing = self.allowlist([{'path': 'result.csv', 'description': 'Unrounded result'}])
        records = package.build(self.root, listing, self.root/'support.zip')
        with zipfile.ZipFile(self.root/'support.zip') as z:
            self.assertEqual(z.read('result.csv'), (self.root/'result.csv').read_bytes())
            self.assertEqual(json.loads(z.read('MANIFEST.json'))['files'], records)

    def test_package_rejects_traversal_and_secrets(self):
        for name in ['../outside.txt', '/absolute.txt', 'C:/private.txt', '.env', '.git/config']:
            with self.subTest(name=name):
                listing = self.allowlist([{'path': name, 'description': 'test'}])
                with self.assertRaises(ValueError):
                    package.build(self.root, listing, self.root/'support.zip')

    def test_package_rejects_case_collisions(self):
        (self.root/'a.txt').write_text('test', encoding='utf-8')
        listing = self.allowlist([{'path': 'a.txt', 'description': 'a'}, {'path': 'A.txt', 'description': 'b'}])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            package.build(self.root, listing, self.root/'support.zip')


if __name__ == '__main__':
    unittest.main()
