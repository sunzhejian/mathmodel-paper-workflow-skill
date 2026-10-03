import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('summary_guard_test', ROOT / 'scripts/summary_guard.py')
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
CONTRACT = {'separate_page': True, 'max_pages': 1, 'heading': '摘要', 'body_heading': '研究背景与问题分析'}
FONT_BUFFER = pymupdf.Font('cjk').buffer
SOURCE = ('#set text(size: 12pt)\n'
          '#align(center)[#text(weight: "bold")[摘要]]\n'
          '#text("合成摘要科学文字 y = 1。")\n'
          '#text(weight: "bold")[关键词：合成；边界]\n\n'
          '= 研究背景与问题分析\n'
          '独立科学正文 $y = 1$。\n')


def make_pdf(path, pages):
    doc = pymupdf.open()
    for content in pages:
        page = doc.new_page()
        page.insert_font(fontname='fixture', fontbuffer=FONT_BUFFER)
        for y, text, size in content:
            page.insert_text((40, y), text, fontname='fixture', fontsize=size)
    doc.save(path)
    doc.close()


class SummaryGuardTests(unittest.TestCase):
    def check_fixture(self, pages, contract=CONTRACT):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'paper.pdf'
            make_pdf(path, pages)
            return GUARD.check_pdf(path, contract)

    def test_same_page_is_rejected(self):
        result = self.check_fixture([[(50, '摘要', 14), (80, '摘要正文。', 12),
                                      (110, '关键词：合成；检验', 12),
                                      (170, '1 研究背景与问题分析', 16)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(result['same_page'])
        self.assertEqual(result['summary_pages'], 1)
        self.assertEqual(result['matches']['body'][0]['maximum_font_size_pt'], 16)

    def test_independent_one_page_summary_passes(self):
        result = self.check_fixture([[(50, '摘 要', 14), (110, '关键字：合成；检验', 12)],
                                     [(50, '一、研究背景与问题分析', 16)]])
        self.assertTrue(result['passed'])
        self.assertEqual(result['status'], 'pass')
        self.assertEqual((result['summary_page'], result['summary_end_page'], result['body_page']), (1, 1, 2))
        self.assertEqual(result['summary_pages'], 1)
        self.assertFalse(result['same_page'])
        self.assertFalse(result['overflow'])

    def test_two_page_summary_overflows_declared_limit(self):
        result = self.check_fixture([[(50, '摘要', 14)], [(110, '关键词：合成', 12)],
                                     [(50, '研究背景与问题分析', 16)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['summary_pages'], 2)
        self.assertTrue(result['overflow'])
        self.assertFalse(result['same_page'])

    def test_continued_summary_on_body_page_is_detected(self):
        result = self.check_fixture([[(50, '摘要', 14)],
                                     [(110, '关键词：合成', 12), (170, '1 研究背景与问题分析', 16)]])
        self.assertFalse(result['passed'])
        self.assertTrue(result['same_page'])
        self.assertTrue(result['overflow'])
        self.assertEqual(result['summary_pages'], 2)

    def test_paragraph_references_are_not_title_matches(self):
        result = self.check_fixture([[(50, '本文在摘要中说明研究背景与问题分析。', 12)],
                                     [(50, '详见研究背景与问题分析中的证据。', 12)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['matches']['summary'], [])
        self.assertEqual(result['matches']['body'], [])

    def test_ambiguous_titles_are_pending_even_when_one_is_larger(self):
        result = self.check_fixture([[(50, '摘要', 14), (110, '关键词：合成', 12), (700, '摘要', 8)],
                                     [(50, '研究背景与问题分析', 16)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(len(result['matches']['summary']), 2)

    def test_missing_summary_end_boundary_is_not_guessed(self):
        result = self.check_fixture([[(50, '摘要', 14), (110, '合成摘要正文。', 12)],
                                     [(50, '研究背景与问题分析', 16)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'pending')
        self.assertIsNone(result['summary_pages'])
        self.assertEqual(result['summary_pages_lower_bound'], 1)

    def test_body_title_before_summary_is_rejected(self):
        result = self.check_fixture([[(50, '研究背景与问题分析', 16)],
                                     [(50, '摘要', 14), (110, '关键词：合成', 12)]])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'fail')

    def test_only_explicit_contract_enforces_separation(self):
        pages = [[(50, '摘要', 14), (110, '关键词：合成', 12), (170, '研究背景与问题分析', 16)]]
        self.assertTrue(self.check_fixture(pages, dict(CONTRACT, separate_page=False))['passed'])

    def test_ensure_separation_is_insertion_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'main.typ'
            path.write_bytes(SOURCE.encode('utf-8'))
            original = path.read_bytes()
            first = GUARD.ensure_separation(path, CONTRACT)
            after = path.read_bytes()
            second = GUARD.ensure_separation(path, CONTRACT)
            self.assertTrue(first['changed'])
            self.assertTrue(first['inserted_pagebreak'])
            self.assertFalse(second['changed'])
            self.assertEqual(after, path.read_bytes())
            self.assertEqual(after.replace(b'#pagebreak()\n\n', b'', 1), original)
            self.assertEqual(first['after_sha256'], hashlib.sha256(after).hexdigest())
            self.assertIn('独立科学正文 $y = 1$。', after.decode('utf-8'))

    def test_crlf_bom_and_comments_are_preserved(self):
        source = SOURCE.replace('\n', '\r\n').replace('\r\n= ', '\r\n/* boundary comment */\r\n= ')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'main.typ'
            original = b'\xef\xbb\xbf' + source.encode('utf-8')
            path.write_bytes(original)
            GUARD.ensure_separation(path, CONTRACT)
            self.assertEqual(path.read_bytes().replace(b'#pagebreak()\r\n\r\n', b'', 1), original)
            self.assertFalse(GUARD.ensure_separation(path, CONTRACT)['changed'])

    def test_unsupported_ambiguous_or_inactive_sources_are_unchanged(self):
        samples = [
            SOURCE.replace('= 研究背景与问题分析', '= 前言\n\n= 研究背景与问题分析'),
            SOURCE + '\n= 研究背景与问题分析\n重复正文。\n',
            SOURCE.replace('#text(weight: "bold")[关键词：合成；边界]', '// 关键词：合成；边界'),
            SOURCE.replace('#align(center)[#text(weight: "bold")[摘要]]', '/* 摘要 */'),
            SOURCE.replace('#align(center)[#text(weight: "bold")[摘要]]', '#let fake-summary = [摘要]'),
            SOURCE.replace('#align(center)[#text(weight: "bold")[摘要]]', '#let fake-summary() = [\n#align(center)[#text(weight: "bold")[摘要]]\n]'),
            '#import "paper-template.typ": *\n' + SOURCE,
            '#abstract-cn[合成摘要]\n= 研究背景与问题分析\n正文。\n',
            SOURCE.replace('= 研究背景与问题分析', '#pagebreak(weak: true)\n= 研究背景与问题分析'),
            SOURCE.replace('= 研究背景与问题分析', '```typ\n= 研究背景与问题分析\n```'),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'custom.typ'
            for source in samples:
                with self.subTest(source=source):
                    path.write_text(source, encoding='utf-8')
                    before = path.read_bytes()
                    with self.assertRaises(ValueError):
                        GUARD.ensure_separation(path, CONTRACT)
                    self.assertEqual(before, path.read_bytes())

    def test_disabled_source_contract_and_invalid_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'main.typ'
            path.write_text('Custom macro template', encoding='utf-8')
            before = path.read_bytes()
            result = GUARD.ensure_separation(path, dict(CONTRACT, separate_page=False))
            self.assertFalse(result['changed'])
            self.assertEqual(result['status'], 'not_required')
            self.assertEqual(before, path.read_bytes())
        for contract in (dict(CONTRACT, max_pages=0), dict(CONTRACT, max_pages=True),
                         dict(CONTRACT, separate_page='yes'), dict(CONTRACT, body_heading='摘要'),
                         dict(CONTRACT, unknown=True)):
            with self.subTest(contract=contract):
                with self.assertRaises(ValueError):
                    GUARD.validate_summary_contract(contract)


if __name__ == '__main__':
    unittest.main()
