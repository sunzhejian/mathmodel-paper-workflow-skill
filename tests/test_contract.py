import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contract = json.loads((ROOT/'examples/workflow-contract.json').read_text(encoding='utf-8'))
        self.contract['audit'] = {'pdf': 'body.pdf', 'pdf_scope': 'body-only', 'first_page': 1, 'last_page': None}
        self.contract['page_requirement'] = {'mode': 'exact', 'count': 1}
        with fitz.open() as doc:
            page = doc.new_page(width=595, height=842)
            for y in range(90, 752, 20):
                page.insert_text((75, y), 'Synthetic contract test body', fontsize=11)
            doc.save(self.root/'body.pdf')

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *extra):
        path = self.root/'contract.json'
        path.write_text(json.dumps(self.contract), encoding='utf-8')
        return subprocess.run([sys.executable, str(ROOT/'scripts/audit_contract.py'), str(path),
                               '--project-root', str(self.root), *extra],
                              capture_output=True, text=True, encoding='utf-8')

    def test_contract_drives_audit_and_renders(self):
        proc = self.cli('--render-dir', 'qa/pages')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads((self.root/'qa/layout.json').read_text(encoding='utf-8'))
        self.assertEqual(report['selected_pages'], 1)
        self.assertEqual(report['blank_limit_percent'], 20)
        self.assertTrue((self.root/'qa/pages/page_001.png').exists())

    def test_dry_run_writes_nothing(self):
        proc = self.cli('--dry-run')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = json.loads(proc.stdout)['arguments']
        self.assertIn('--exact-pages', args)
        self.assertNotIn('--max-pages', args)
        self.assertFalse((self.root/'qa').exists())

    def test_maximum_mode_and_no_threshold(self):
        self.contract['page_requirement'] = {'mode': 'maximum', 'count': 2}
        self.contract['blank_limit_percent'] = None
        proc = self.cli('--dry-run')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = json.loads(proc.stdout)['arguments']
        self.assertIn('--max-pages', args)
        self.assertNotIn('--blank-limit', args)

    def test_combined_pdf_requires_explicit_boundary(self):
        self.contract['audit']['pdf_scope'] = 'combined'
        self.assertEqual(self.cli().returncode, 2)
        self.contract['audit']['last_page'] = 1
        self.assertEqual(self.cli().returncode, 0)

    def test_invalid_numeric_inputs(self):
        for bad in [True, -1, 2.5, '31']:
            with self.subTest(count=bad):
                self.contract['page_requirement']['count'] = bad
                self.assertEqual(self.cli().returncode, 2)
        self.contract['page_requirement']['count'] = 1
        for bad in [True, float('nan'), float('inf'), -1, 101]:
            with self.subTest(blank=bad):
                self.contract['blank_limit_percent'] = bad
                self.assertEqual(self.cli().returncode, 2)
        self.assertFalse((self.root/'qa').exists())

    def test_paths_and_report_collision_preserve_inputs(self):
        original = (self.root/'body.pdf').read_bytes()
        for report in ['../escaped.json', 'body.pdf', 'contract.json', 'C:/outside.json']:
            with self.subTest(report=report):
                self.assertEqual(self.cli('--report', report).returncode, 2)
        self.assertEqual((self.root/'body.pdf').read_bytes(), original)
        self.contract['audit']['pdf'] = '../body.pdf'
        self.assertEqual(self.cli().returncode, 2)

    def test_preserves_previous_report_and_previews(self):
        self.assertEqual(self.cli('--render-dir', 'qa/pages').returncode, 0)
        before = (self.root/'qa/layout.json').read_bytes()
        self.assertEqual(self.cli().returncode, 2)
        self.assertEqual(self.cli('--report', 'qa/another.json', '--render-dir', 'qa/pages').returncode, 2)
        self.assertEqual((self.root/'qa/layout.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
