import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import pymupdf as fitz
from bigdata_fixture import fill, font_dir

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = load("check_mathorcup_bigdata_pdf")
PREPARE = load("prepare_mathorcup_bigdata_template")
TYPST = os.environ.get("MATHMODEL_TYPST_EXE") or shutil.which("typst")
LATEX = os.environ.get("MATHMODEL_XELATEX_EXE") or shutil.which("xelatex")
CJK_FONTS = os.environ.get("MATHMODEL_CJK_FONT_DIR")


class BigDataChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, body=3, appendix=1, wrong_footer=False, header=False):
        pdf = self.root / "fixture.pdf"
        total = 2 + body + appendix
        with fitz.open() as doc:
            for i in range(total):
                page = doc.new_page(width=595.276, height=841.89)
                if header:
                    page.insert_text((72, 25), "Team # 1234567")
                content = ("队伍编号 MCB2600001\n赛道 A\n合成标题\n摘要\n内容\n关键词：测试" if i == 0 else
                           "目录\n数据与模型 1\n结果 2\n附录 4" if i == 1 else
                           "附录\n合成源代码" if i == 2 + body else "模型、结果与参考文献")
                page.insert_text((72, 110), content, fontname="china-s", fontsize=12)
                if i >= 2:
                    number = str(i - 1 + int(wrong_footer))
                    page.insert_text((294, 815), number, fontsize=10)
            doc.save(pdf)
        data = {"schema_version": 1, "family": "mathorcup-bigdata", "contest_year": 2026,
                "format_rules_year": 2025, "rules_status": "provisional", "team_number": "MCB2600001", "track": "A",
                "summary_last_page": 1, "contents_last_page": 2, "body_first_page": 3, "body_last_page": 2 + body,
                "appendix_first_page": 3 + body if appendix else None, "total_pages": total}
        meta = self.root / "fixture.json"
        meta.write_text(json.dumps(data), encoding="utf-8")
        return pdf, meta, data

    def test_front_matter_and_appendix_are_separate_from_body_limit(self):
        pdf, meta, _ = self.fixture(body=30, appendix=8)
        result = CHECK.verify(pdf, meta, expected_year=2026)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["body_pages"], 30)
        self.assertEqual(result["appendix_pages"], 8)
        self.assertTrue(result["current_format_confirmation_required"])
        self.assertNotIn("MCB2600001", json.dumps(result))

    def test_31_body_pages_are_rejected(self):
        pdf, meta, _ = self.fixture(body=31)
        self.assertIn("Body exceeds the selected page limit", CHECK.verify(pdf, meta)["failures"])

    def test_mcm_header_and_wrong_body_footer_are_rejected(self):
        pdf, meta, _ = self.fixture(wrong_footer=True, header=True)
        findings = CHECK.verify(pdf, meta)["failures"]
        self.assertTrue(any("header band" in item for item in findings))
        self.assertTrue(any("centered Arabic" in item for item in findings))

    def test_wrong_boundary_or_unconfirmed_baseline_cannot_be_hidden(self):
        pdf, meta, data = self.fixture()
        data.update(summary_last_page=2, contents_last_page=3, body_first_page=4, body_last_page=4,
                    appendix_first_page=5, rules_status="official")
        meta.write_text(json.dumps(data), encoding="utf-8")
        result = CHECK.verify(pdf, meta)
        self.assertFalse(result["passed"])
        self.assertTrue(any("baseline/status" in x for x in result["failures"]))
        self.assertTrue(any("appendix heading" in x for x in result["failures"]))

    def test_wrong_track_and_edition_are_detected(self):
        pdf, meta, data = self.fixture()
        data["track"] = "B"
        meta.write_text(json.dumps(data), encoding="utf-8")
        result = CHECK.verify(pdf, meta, expected_year=2027)
        self.assertIn("Visible track differs from compiled metadata", result["failures"])
        self.assertTrue(any("selected edition" in x for x in result["failures"]))

    def test_initialization_and_reports_preserve_existing_files(self):
        # This check also protects a draft with unfilled user fields.
        folder = self.root / "new-draft"
        entry = PREPARE.prepare("latex", folder)
        before = entry.read_bytes()
        with self.assertRaises(ValueError):
            PREPARE.prepare("typst", folder)
        self.assertEqual(entry.read_bytes(), before)
        pdf, meta, _ = self.fixture()
        original = pdf.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(pdf)]), 2)
        self.assertEqual(pdf.read_bytes(), original)
        report = self.root / "check.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(report)]), 0)
        saved = report.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(report)]), 2)
        self.assertEqual(report.read_bytes(), saved)

    def test_scaffold_and_malformed_metadata_are_not_accepted(self):
        pdf, meta, data = self.fixture()
        data.update(team_number="MCB26XXXX", track="X")
        meta.write_text(json.dumps(data), encoding="utf-8")
        result = CHECK.verify(pdf, meta)
        self.assertFalse(result["passed"])
        self.assertTrue(any("unfilled" in item for item in result["failures"]))
        data["track"] = ["A"]
        meta.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "track must be a string"):
            CHECK.verify(pdf, meta)


class BigDataCompilerChecks(unittest.TestCase):
    def run_cmd(self, args, folder):
        result = subprocess.run(args, cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-3500:])
        return result

    def assert_output(self, pdf, meta, appendix):
        result = CHECK.verify(pdf, meta, expected_year=2026)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["body_pages"], 2)
        self.assertEqual(result["total_pages"], 5 if appendix else 4)
        with fitz.open(pdf) as doc:
            contents = compact(doc[1].get_text())
            self.assertIn("数据与模型", contents)
            self.assertIn("检验与结果", contents)
            self.assertIn("参考文献", contents)
            self.assertEqual("附录" in contents, appendix)
            self.assertNotIn("\ufffd", "".join(p.get_text() for p in doc))

    @unittest.skipUnless(LATEX, "XeLaTeX unavailable; Big Data compiler check not executed")
    def test_latex_compilation_and_dynamic_body_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "latex"
            PREPARE.prepare("latex", folder)
            (folder / "build").mkdir()
            version = self.run_cmd([LATEX, "--version"], folder).stdout
            flags = ["--disable-installer"] if "MiKTeX" in version else []
            for appendix in (True, False):
                with self.subTest(appendix=appendix):
                    fill(folder, "latex", appendix=appendix, ai=True)
                    for _ in range(3):
                        self.run_cmd([LATEX, *flags, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "-output-directory=build", "main.tex"], folder)
                    self.assert_output(folder / "build/main.pdf", folder / "build/main.bigdata.json", appendix)

    @unittest.skipUnless(TYPST and CJK_FONTS, "Typst or explicit CJK font directory unavailable; Big Data compiler check not executed")
    def test_typst_compilation_boundaries_and_summary_overflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "typst"
            PREPARE.prepare("typst", folder)
            (folder / "build").mkdir()
            fonts = font_dir(folder)
            font_args = ["--ignore-system-fonts", "--font-path", str(fonts)]
            for appendix in (True, False):
                with self.subTest(appendix=appendix):
                    fill(folder, "typst", appendix=appendix, ai=True)
                    self.run_cmd([TYPST, "compile", *font_args, "main.typ", "build/main.pdf"], folder)
                    metadata = self.run_cmd([TYPST, "query", *font_args, "main.typ", "<bd-boundary>", "--field", "value", "--one"], folder).stdout
                    (folder / "build/main.bigdata.json").write_text(metadata, encoding="utf-8")
                    self.assert_output(folder / "build/main.pdf", folder / "build/main.bigdata.json", appendix)
            (folder / "summary.typ").write_text("合成摘要溢出测试。" * 650, encoding="utf-8")
            self.run_cmd([TYPST, "compile", *font_args, "main.typ", "build/main.pdf"], folder)
            metadata = self.run_cmd([TYPST, "query", *font_args, "main.typ", "<bd-boundary>", "--field", "value", "--one"], folder).stdout
            (folder / "build/main.bigdata.json").write_text(metadata, encoding="utf-8")
            result = CHECK.verify(folder / "build/main.pdf", folder / "build/main.bigdata.json")
            self.assertFalse(result["passed"])
            self.assertGreater(json.loads(metadata)["summary_last_page"], 1)


def compact(value):
    return CHECK.compact(value)


if __name__ == "__main__":
    unittest.main()
