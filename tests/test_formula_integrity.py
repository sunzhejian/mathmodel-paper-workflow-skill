import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('formula_integrity_test', ROOT / 'scripts/check_formula_integrity.py')
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)

BAD = ('#set math.equation(numbering: "(1)")\n'
       '#text("Service quantity: ")$ u_t $#text("=min(")$ y_t $#text(", ")'
       '$ I_(t-1) $#text("+")$ q_t $#text("). Inventory: ")'
       '$ I_t $#text("=")$ I_(t-1) $#text("+")$ q_t $#text("-")$ u_t $#text(".")\n')
GOOD = ('#set math.equation(numbering: "(1)")\n'
        'The quantity $u_t$ uses $y_t$ and $I_(t-1)$ with $q_t$.\n\n'
        '$ u_t = min(y_t, I_(t-1) + q_t) $\n\n'
        '$ I_t = I_(t-1) + q_t - u_t $\n')


def make_rows_pdf(path, orphan=True, complete=False):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    for index, y in enumerate((140, 220, 300), 1):
        content = 'x = 0' if complete else 'x'
        page.insert_text((296 if not complete else 282, y), content, fontsize=12, fontname='tiit')
        page.insert_text((515, y), f'({index})', fontsize=12)
        if orphan:
            page.insert_text((70, y - 30), '=' if index % 2 else '+', fontsize=12)
    doc.save(path)
    doc.close()


class FormulaIntegrityTests(unittest.TestCase):
    def test_fragmented_min_and_inventory_relations_fail(self):
        report = GUARD.check_source(BAD)
        self.assertEqual(report['status'], 'fail')
        issue = next(i for i in report['issues'] if i['code'] == 'fragmented_relation')
        self.assertIn('=min(', issue['orphan_separators'])
        self.assertGreaterEqual(len(issue['locations']), 7)
        self.assertEqual(issue['locations'][0]['line'], 2)
        self.assertGreater(issue['locations'][0]['column'], 1)
        self.assertFalse(report['block_defaults'])

    def test_actual_source_dollar_boundary_is_display_cause(self):
        report = GUARD.check_source('Value $x_t$, complete relation $ x_t = 0 $.')
        self.assertTrue(report['passed'])
        self.assertFalse(report['equations'][0]['natural_display'])
        self.assertTrue(report['equations'][1]['natural_display'])

    def test_normal_inline_and_complete_display_pass(self):
        report = GUARD.check_source(GOOD)
        self.assertTrue(report['passed'])
        self.assertEqual(report['display_count'], 2)
        self.assertEqual(report['atomic_display_count'], 0)

    def test_short_complete_equations_are_not_flagged(self):
        text = '$ x = 0 $\n\n$ y = 1 $\n\n$ E = m c^2 $'
        self.assertTrue(GUARD.check_source(text)['passed'])

    def test_legitimate_cases_system_is_not_flagged(self):
        text = '$ cases(x + y = 1, x - y = 0) $'
        self.assertTrue(GUARD.check_source(text)['passed'])

    def test_one_intentional_atomic_display_not_a_failure(self):
        self.assertTrue(GUARD.check_source('One selected state:\n\n$ x_t $')['passed'])

    def test_narrative_display_variable_cluster_needs_review(self):
        report = GUARD.check_source('$ x $ denotes demand, $ y $ denotes stock and $ z $ denotes supply.')
        self.assertEqual(report['status'], 'review')
        self.assertEqual(report['issues'][0]['code'], 'display_variable_cluster')

    def test_comments_strings_and_raw_examples_are_excluded(self):
        text = '// $ x $ = $ y $\n/* nested /* $ z $ */ comment */\n#text("$ u $ = $ v $")\n```typ\n$ a $ = $ b $\n```\n$x$'
        report = GUARD.check_source(text)
        self.assertTrue(report['passed'])
        self.assertEqual(report['equation_count'], 1)
        self.assertEqual(report['equations'][0]['body'], 'x')

    def test_escaped_dollar_is_not_an_equation(self):
        report = GUARD.check_source(r'Price \$10; variable $x$ remains inline.')
        self.assertTrue(report['passed'])
        self.assertEqual(report['equation_count'], 1)

    def test_unit_string_containing_dollar_does_not_close_equation(self):
        report = GUARD.check_source('$ p = 1 "dollar $ per item" $')
        self.assertEqual(report['equation_count'], 1)
        self.assertTrue(report['passed'])

    def test_unmatched_delimiter_needs_review(self):
        report = GUARD.check_source('$x and no end')
        self.assertEqual(report['status'], 'review')

    def test_unclosed_comments_needs_review(self):
        report = GUARD.check_source('/* missing end $ x $ = $ y $')
        self.assertEqual(report['status'], 'review')
        self.assertEqual(report['issues'][0]['code'], 'source_lexing_incomplete')

    def test_global_block_default_warns_about_scope(self):
        report = GUARD.check_source('#set math.equation(block: true, numbering: "(1)")\n$x$ and $y$.')
        self.assertEqual(report['status'], 'review')
        self.assertTrue(report['block_defaults'])

    def test_show_equation_block_default_warns(self):
        report = GUARD.check_source('#show math.equation: set math.equation(block: true)\n$x$')
        self.assertEqual(report['status'], 'review')

    def test_breakable_block_rule_is_not_block_true_equation_rule(self):
        text = '#show math.equation: set block(breakable: true)\n$x$'
        self.assertTrue(GUARD.check_source(text)['passed'])

    def test_numbering_rule_alone_is_not_a_block_default(self):
        self.assertTrue(GUARD.check_source('#set math.equation(numbering: "(1)")\n$x$')['passed'])

    def test_explicit_appendix_boundary_excludes_only_declared_heading(self):
        text = GOOD + '\n= Appendix\n' + BAD
        self.assertEqual(GUARD.check_source(text)['status'], 'fail')
        self.assertTrue(GUARD.check_source(text, stop_at_heading='Appendix')['passed'])
        with self.assertRaises(ValueError):
            GUARD.check_source(text, stop_at_heading='Not present')

    def test_pdf_orphan_operators_and_numbered_atoms_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.pdf'
            make_rows_pdf(path)
            report = GUARD.check_pdf(path)
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(report['issues'][0]['page'], 1)
            self.assertEqual(len(report['issues'][0]['equation_rows']), 3)
            self.assertEqual(len(report['issues'][0]['orphan_operator_rows']), 3)

    def test_pdf_short_complete_equations_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.pdf'
            make_rows_pdf(path, orphan=False, complete=True)
            self.assertTrue(GUARD.check_pdf(path)['passed'])

    def test_pdf_atomic_run_without_operators_is_review_not_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.pdf'
            make_rows_pdf(path, orphan=False)
            self.assertEqual(GUARD.check_pdf(path)['status'], 'review')

    def test_blank_or_raster_only_pdf_is_not_certified(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'blank.pdf'
            with pymupdf.open() as doc:
                doc.new_page()
                doc.save(path)
            self.assertEqual(GUARD.check_pdf(path)['status'], 'review')

    def test_explicit_pdf_pages_and_invalid_ranges(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.pdf'
            make_rows_pdf(path)
            self.assertEqual(GUARD.check_pdf(path, page_numbers=[1])['checked_pages'], [1])
            for selected in ([], [0], [1, 1], [2], [True]):
                with self.subTest(selected=selected), self.assertRaises(ValueError):
                    GUARD.check_pdf(path, page_numbers=selected)

    def test_checks_never_rewrite_source_or_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            source, pdf = Path(folder) / 'main.typ', Path(folder) / 'main.pdf'
            source.write_text(BAD, encoding='utf-8')
            make_rows_pdf(pdf)
            hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, pdf)]
            report = GUARD.check(source, pdf)
            self.assertFalse(report['manuscript_modified'])
            self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, pdf)])

    def test_cli_outputs_locations_and_nonzero_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'main.typ', Path(folder) / 'report.json'
            source.write_text(BAD, encoding='utf-8')
            result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/check_formula_integrity.py'),
                                     str(source), '--output', str(output)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['status'], 'fail')

    def test_cli_report_cannot_overwrite_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'main.typ'
            source.write_text(GOOD, encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_formula_integrity.py'),
                                     str(source), '--output', str(source)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_text(encoding='utf-8'), GOOD)

    @unittest.skipUnless(os.environ.get('MATHMODEL_TYPST_EXE'), 'Set MATHMODEL_TYPST_EXE for real compilation regression')
    def test_real_typst_whitespace_display_and_numbering_regression(self):
        compiler = os.environ['MATHMODEL_TYPST_EXE']
        with tempfile.TemporaryDirectory() as folder:
            for name, source_text, expected in [('bad', BAD, 'fail'), ('good', GOOD, 'pass')]:
                with self.subTest(case=name):
                    source, pdf = Path(folder) / f'{name}.typ', Path(folder) / f'{name}.pdf'
                    source.write_text('#set page(width: 21cm, height: 29.7cm, margin: 2.5cm)\n' + source_text, encoding='utf-8')
                    subprocess.run([compiler, 'compile', str(source), str(pdf)], check=True,
                                   capture_output=True, text=True, encoding='utf-8', timeout=60)
                    self.assertEqual(GUARD.check_source(source.read_text(encoding='utf-8'))['status'], expected)
                    self.assertEqual(GUARD.check_pdf(pdf)['status'], expected)


if __name__ == '__main__':
    unittest.main()
