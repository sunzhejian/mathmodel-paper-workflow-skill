import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import pymupdf

spec=importlib.util.spec_from_file_location('render_guard',Path(__file__).resolve().parents[1]/'scripts/rendering_guard.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CONTRACT={'schema_version':1,'engine':'typst','fonts':{'body':'SimSun','heading':'SimHei','latin':'Times New Roman'},'body_size_pt':12,'margins_cm':2.5,'figure_width_mm':160,'minimum_dpi':300}

class RenderingGuardTests(unittest.TestCase):
    def test_browser_valid_foreignobject_is_rejected_for_typst(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'figure.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div>label</div></foreignObject></svg>')
            self.assertFalse(m.svg_compatibility(p)['direct_embedding_ready'])
            self.assertTrue(m.svg_compatibility(p,'browser')['direct_embedding_ready'])
    def test_plain_vector_is_not_declared_visually_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'figure.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L5 5"/></svg>')
            r=m.svg_compatibility(p);self.assertTrue(r['direct_embedding_ready']);self.assertIn('actual final-PDF',r['next_step'])
    def test_font_profile_preserves_prose_and_refuses_missing_font(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'main.typ';original='#set text(font: "Wrong", size: 11.5pt)\n正文模型 y = 1。\n';p.write_text(original,encoding='utf-8')
            with patch.object(m,'font_names',return_value={'SimSun','SimHei','Times New Roman'}):m.apply_profile(p,CONTRACT,Path('compiler'))
            self.assertIn('正文模型 y = 1。',p.read_text(encoding='utf-8'))
            before=p.read_bytes()
            with patch.object(m,'font_names',return_value=set()):
                with self.assertRaises(ValueError):m.apply_profile(p,CONTRACT,Path('compiler'))
            self.assertEqual(before,p.read_bytes())
    def test_no_template_declaration_is_not_silently_patched(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'custom.typ';p.write_text('Custom template\n')
            with patch.object(m,'font_names',return_value=set(CONTRACT['fonts'].values())):
                with self.assertRaises(ValueError):m.apply_profile(p,CONTRACT,Path('compiler'))

    def test_css_resources_detected_for_both_targets(self):
        samples = [
            '<style>@import "theme.css";</style>',
            '<style>@font-face {src: url("https://example.test/font.woff")}</style>',
            '<rect fill="url(//example.test/paint.svg#p)"/>',
            '<image href="photo.png"/>',
            '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="other.svg#p"/>',
            '<feImage href="https://example.test/image.png"/>',
        ]
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'figure.svg'
            for content in samples:
                p.write_text('<svg xmlns="http://www.w3.org/2000/svg">' + content + '</svg>')
                for engine in ('typst', 'browser'):
                    with self.subTest(content=content, engine=engine):
                        result = m.svg_compatibility(p, engine)
                        self.assertFalse(result['direct_embedding_ready'])
                        self.assertTrue(any('external resources' in reason for reason in result['reasons']))

    def test_hyperlinks_and_bundled_fragment_resources_are_not_external_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'figure.svg'
            p.write_text('<svg xmlns="http://www.w3.org/2000/svg">'
                         '<a href="https://diagrams.net/?text=var(test)" aria-label="@import"><text>link</text></a>'
                         '<image href="data:image/png;base64,AA=="/>'
                         '<use href="#shape"/><rect fill="url(#paint)"/>'
                         '<!-- foreignObject light-dark(black, white) -->'
                         '<style>/* @import "unused.css" */</style></svg>')
            self.assertTrue(m.svg_compatibility(p)['direct_embedding_ready'])

    def test_dynamic_css_is_target_specific_and_stylesheet_pi_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'figure.svg'
            p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect fill="var(--fill)"/></svg>')
            self.assertFalse(m.svg_compatibility(p)['direct_embedding_ready'])
            self.assertTrue(m.svg_compatibility(p, 'browser')['direct_embedding_ready'])
            p.write_text('<?xml-stylesheet href="theme.css"?>'
                         '<svg xmlns="http://www.w3.org/2000/svg"/>')
            self.assertFalse(m.svg_compatibility(p)['direct_embedding_ready'])

    def test_unknown_svg_target_and_non_svg_root_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'other.xml'
            p.write_text('<html/>')
            with self.assertRaises(ValueError):
                m.svg_compatibility(p, 'unknown')
            with self.assertRaises(ValueError):
                m.svg_compatibility(p)

    def test_multiline_profile_is_idempotent_and_preserves_nonfont_settings(self):
        original = ('#set text(\n  font: ("Wrong", "Other"),\n  size: 10pt,\n'
                    '  tracking: 0.1pt, fill: rgb("#123456"), lang: "en",\n)\n'
                    '#show heading.where(level: 1): set text(font: "Wrong", size: 16pt, weight: "bold")\n'
                    '#show heading: set text(\n  font: "Other", size: 13pt,\n)\n'
                    '正文模型 $y = 1$。\n')
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'main.typ'
            p.write_text(original, encoding='utf-8')
            with patch.object(m, 'font_names', return_value=set(CONTRACT['fonts'].values())):
                first = m.apply_profile(p, CONTRACT, Path('compiler'))
                first_bytes = p.read_bytes()
                second = m.apply_profile(p, CONTRACT, Path('compiler'))
            result = p.read_text(encoding='utf-8')
            self.assertTrue(first['changed'])
            self.assertFalse(second['changed'])
            self.assertEqual(first_bytes, p.read_bytes())
            self.assertEqual(result.count('font: "SimHei"'), 2)
            self.assertIn('tracking: 0.1pt, fill: rgb("#123456"), lang: "en"', result)
            self.assertIn('size: 16pt, weight: "bold"', result)
            self.assertIn('正文模型 $y = 1$。', result)
            self.assertEqual(first['after_sha256'], hashlib.sha256(first_bytes).hexdigest())

    def test_profile_adds_explicit_heading_default_once(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'main.typ'
            p.write_text('#set text(font: "Wrong", size: 10pt)\n正文\n', encoding='utf-8')
            with patch.object(m, 'font_names', return_value=set(CONTRACT['fonts'].values())):
                first = m.apply_profile(p, CONTRACT, Path('compiler'))
                second = m.apply_profile(p, CONTRACT, Path('compiler'))
            self.assertTrue(first['heading_default_added'])
            self.assertFalse(second['changed'])
            self.assertEqual(p.read_text(encoding='utf-8').count('#show heading:'), 1)

    def test_custom_ambiguous_or_comment_only_declarations_leave_source_intact(self):
        samples = [
            '/* #set text(font: "Wrong") */\n正文\n',
            '```typ\n#set text(font: "Wrong")\n```\n正文\n',
            '#let example = [\n#set text(font: "Wrong")\n]\n正文\n',
            '#set text(font: "Wrong")\n#set text(size: 10pt)\n正文\n',
            '#set text(font: "Wrong")\n#show heading: it => [#it.body]\n正文\n',
            '#set text(font: "Wrong", font: "Duplicate")\n正文\n',
        ]
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'custom.typ'
            for original in samples:
                with self.subTest(original=original):
                    p.write_text(original, encoding='utf-8')
                    before = p.read_bytes()
                    with patch.object(m, 'font_names', return_value=set(CONTRACT['fonts'].values())):
                        with self.assertRaises(ValueError):
                            m.apply_profile(p, CONTRACT, Path('compiler'))
                    self.assertEqual(before, p.read_bytes())

    def test_profile_preserves_bom_crlf_and_ignores_inactive_font_examples(self):
        original = ('/*\r\n#set text(font: "Ignored")\r\n*/\r\n'
                    '#set text(font: "Wrong", size: 10pt)\r\n正文\r\n')
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'main.typ'
            p.write_bytes(b'\xef\xbb\xbf' + original.encode('utf-8'))
            with patch.object(m, 'font_names', return_value=set(CONTRACT['fonts'].values())):
                m.apply_profile(p, CONTRACT, Path('compiler'))
            self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\n', p.read_bytes().replace(b'\r\n', b''))
            self.assertIn('#set text(font: "Ignored")', p.read_text(encoding='utf-8-sig'))

    def test_font_inventory_and_profile_pass_through_restricted_environment(self):
        environment = {'SystemRoot': 'C:/Windows'}
        completed = Mock(stdout=' SimSun\nSimHei\nTimes New Roman\n\n')
        with patch.object(m.subprocess, 'run', return_value=completed) as run:
            names = m.font_names(Path('compiler'), Path('fonts'), env=environment)
        self.assertEqual(names, set(CONTRACT['fonts'].values()))
        self.assertIs(run.call_args.kwargs['env'], environment)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'main.typ'
            p.write_text('#set text(font: "Wrong")\n正文\n', encoding='utf-8')
            with patch.object(m, 'font_names', return_value=names) as inventory:
                m.apply_profile(p, CONTRACT, Path('compiler'), env=environment)
            self.assertIs(inventory.call_args.kwargs['env'], environment)

    def test_nonfinite_contract_values_are_rejected(self):
        for value in (float('nan'), float('inf'), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    m.validate_contract(dict(CONTRACT, body_size_pt=value))

    def test_font_matching_accepts_actual_postscript_style_but_not_other_families(self):
        self.assertTrue(m._font_family_matches('Times New Roman', 'ABCDEF+TimesNewRomanPS-BoldMT'))
        self.assertTrue(m._font_family_matches('Noto Sans SC', 'NotoSansSC-Thin'))
        self.assertFalse(m._font_family_matches('SimSun', 'NSimSun'))
        self.assertFalse(m._font_family_matches('SimSun', 'SimSun-ExtB'))
        self.assertFalse(m._font_family_matches('Arial', 'Arial Narrow'))
        self.assertFalse(m._font_family_matches('宋体', '黑体'))

    def test_pdf_unused_embedded_font_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'unused.pdf'
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_font(fontname='proof', fontbuffer=pymupdf.Font('tiro').buffer)
            page.insert_text((50, 50), 'Visible other-family text', fontname='helv')
            doc.save(p)
            doc.close()
            contract = dict(CONTRACT, fonts=dict.fromkeys(('body', 'heading', 'latin'), 'Nimbus Roman'))
            result = m.pdf_font_check(p, contract)
            self.assertTrue(all(result['expected_fonts_present'].values()))
            self.assertFalse(any(result['expected_fonts_used'].values()))
            self.assertFalse(result['passed'])

    def test_pdf_actual_font_identity_beats_spoofed_resource_name(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'spoofed.pdf'
            doc = pymupdf.open()
            page = doc.new_page()
            xref = page.insert_font(fontname='proof', fontbuffer=pymupdf.Font('helv').buffer)
            doc.xref_set_key(xref, 'BaseFont', '/SimSun')
            page.insert_text((50, 50), 'Visible wrong-family text', fontname='proof')
            doc.save(p)
            doc.close()
            contract = dict(CONTRACT, fonts=dict.fromkeys(('body', 'heading', 'latin'), 'SimSun'))
            result = m.pdf_font_check(p, contract)
            self.assertIn('SimSun', result['resource_font_names'])
            self.assertFalse(any(result['expected_fonts_present'].values()))
            self.assertFalse(result['passed'])

    def test_pdf_family_presence_does_not_claim_role_or_size_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'used.pdf'
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_font(fontname='proof', fontbuffer=pymupdf.Font('tiro').buffer)
            page.insert_text((50, 50), 'Visible expected-family text', fontname='proof', fontsize=7)
            doc.save(p)
            doc.close()
            contract = dict(CONTRACT, fonts=dict.fromkeys(('body', 'heading', 'latin'), 'Nimbus Roman'))
            result = m.pdf_font_check(p, contract)
            self.assertTrue(result['passed'])
            self.assertFalse(result['font_roles_verified'])
            self.assertFalse(result['body_size_verified'])
            self.assertFalse(result['body_font_weight_verified'])
            self.assertFalse(m.pdf_font_check(p, dict(contract, minimum_pages=2))['passed'])

    def test_unused_correct_font_and_spoofed_wrong_font_do_not_combine_into_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'combined.pdf'
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_font(fontname='unused', fontbuffer=pymupdf.Font('tiro').buffer)
            xref = page.insert_font(fontname='spoof', fontbuffer=pymupdf.Font('helv').buffer)
            doc.xref_set_key(xref, 'BaseFont', '/NimbusRoman-Regular')
            page.insert_text((50, 50), 'Visible wrong-family text', fontname='spoof')
            doc.save(p)
            doc.close()
            contract = dict(CONTRACT, fonts=dict.fromkeys(('body', 'heading', 'latin'), 'Nimbus Roman'))
            result = m.pdf_font_check(p, contract)
            self.assertTrue(all(result['expected_fonts_present'].values()))
            self.assertFalse(any(result['expected_fonts_used'].values()))
            self.assertFalse(result['passed'])
if __name__=='__main__':unittest.main()
