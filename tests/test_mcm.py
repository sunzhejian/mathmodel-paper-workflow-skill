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
from mcm_fixture import fill

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/"scripts"/(name+".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = load("check_mcm_pdf")
PREPARE = load("prepare_mcm_template")
INVENTORY = load("template_inventory")
TYPST = os.environ.get("MATHMODEL_TYPST_EXE") or shutil.which("typst")
LATEX = os.environ.get("MATHMODEL_XELATEX_EXE") or shutil.which("xelatex")


class MCMChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, solution=4, ai=0, wrong_header=False, duplicate_summary=False):
        pdf = self.root/"fixture.pdf"
        total = solution+ai
        with fitz.open() as document:
            for i in range(total):
                page = document.new_page(width=595, height=842)
                page.insert_text((72, 45), "Team # 1234567", fontsize=12)
                page.insert_text((380, 45), f"Page {i+1} of {total+int(wrong_header)}", fontsize=12)
                if i == 0 or (duplicate_summary and i == 1):
                    page.insert_text((72, 100), "Problem Chosen: B", fontsize=12)
                    page.insert_text((72, 125), "2027 MCM/ICM Summary Sheet", fontsize=12)
                    page.insert_text((72, 150), "Team Control Number: 1234567", fontsize=12)
                elif i == solution and ai:
                    page.insert_text((72, 150), "Report on Use of AI Tools", fontsize=14)
                else:
                    page.insert_text((72, 150), "Synthetic fixture content", fontsize=12)
            document.save(pdf)
        meta = {"schema_version": 1, "family": "mcm-icm", "contest_year": 2027,
                "problem": "B", "team_control_number": "1234567", "summary_last_page": 1,
                "solution_last_page": solution, "ai_first_page": solution+1 if ai else None,
                "total_pages": total}
        metadata = self.root/"fixture.json"
        metadata.write_text(json.dumps(meta), encoding="utf-8")
        return pdf, metadata, meta

    def test_solution_and_ai_report_have_separate_limits(self):
        pdf, meta, _ = self.fixture(solution=17, ai=10)
        result = CHECK.verify(pdf, meta, expected_year=2027)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["solution_pages"], 17)
        self.assertEqual(result["ai_report_pages"], 10)
        self.assertNotIn("1234567", json.dumps(result))

    def test_26_solution_pages_are_rejected(self):
        pdf, meta, _ = self.fixture(solution=26)
        self.assertIn("Solution exceeds the selected page limit", CHECK.verify(pdf, meta)["failures"])

    def test_wrong_headers_and_duplicate_summary_are_detected(self):
        pdf, meta, _ = self.fixture(wrong_header=True, duplicate_summary=True)
        result = CHECK.verify(pdf, meta)
        self.assertFalse(result["passed"])
        self.assertIn("Expected one Summary Sheet on physical page 1", result["failures"])
        self.assertTrue(any("header page" in item for item in result["failures"]))

    def test_ai_boundary_cannot_hide_solution_pages(self):
        pdf, meta, data = self.fixture(solution=5, ai=2)
        data["solution_last_page"] = 4
        data["ai_first_page"] = 5
        meta.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("AI boundary page has no Report on Use of AI Tools heading", CHECK.verify(pdf, meta)["failures"])

    def test_overflow_unfilled_config_and_wrong_year_are_detected(self):
        pdf, meta, data = self.fixture()
        data.update(summary_last_page=2, team_control_number="0000000", problem="X")
        meta.write_text(json.dumps(data), encoding="utf-8")
        result = CHECK.verify(pdf, meta, expected_year=2026)
        self.assertFalse(result["passed"])
        self.assertIn("Summary Sheet must occupy exactly the first page", result["failures"])
        self.assertIn("Contest year differs from the selected edition", result["failures"])

    def test_existing_reports_and_inputs_are_preserved(self):
        pdf, meta, _ = self.fixture()
        before = pdf.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(pdf)]), 2)
        self.assertEqual(pdf.read_bytes(), before)
        report = self.root/"check.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(report)]), 0)
        report_before = report.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECK.main([str(pdf), "--metadata", str(meta), "--report", str(report)]), 2)
        self.assertEqual(report.read_bytes(), report_before)

    def test_soft_hyphen_in_sheet_label_does_not_cause_false_failure(self):
        self.assertEqual(CHECK.normalized("Team Control Num\u00ad\nber"), "Team Control Number")

    def test_unfilled_visible_scaffold_is_rejected(self):
        pdf, meta, _ = self.fixture()
        with fitz.open(pdf) as document:
            document[2].insert_text((72, 180), "REPLACE_SOLUTION", fontsize=12)
            document.save(self.root/"unfilled.pdf")
        result = CHECK.verify(self.root/"unfilled.pdf", meta)
        self.assertIn("Page 3: unfilled template content", result["failures"])

    def test_prepare_refuses_to_overwrite_existing_configuration(self):
        target = self.root/"paper"
        entry = PREPARE.prepare("latex", target)
        (target/"config.tex").write_text("user-owned configuration", encoding="utf-8")
        with self.assertRaises(ValueError):
            PREPARE.prepare("latex", target)
        self.assertEqual((target/"config.tex").read_text(encoding="utf-8"), "user-owned configuration")
        self.assertTrue(entry.is_file())

    def test_project_template_takes_precedence_without_modifying_vendor(self):
        skill = self.root/"skill"
        vendor = skill/"vendor/MathModelAgent/skills/5writing/templates/en/mcm-latex"
        vendor.mkdir(parents=True)
        (vendor/"main.tex").write_text("fixed vendor source", encoding="utf-8")
        adaptation = skill/"assets/templates/en/mcm-latex"
        adaptation.mkdir(parents=True)
        (adaptation/"main.tex").write_text("project adaptation", encoding="utf-8")
        records = INVENTORY.inspect(self.root, skill)["available"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["template_source"], "project-adaptation")
        self.assertEqual((vendor/"main.tex").read_text(encoding="utf-8"), "fixed vendor source")


class MCMCompilerChecks(unittest.TestCase):
    def run_cmd(self, args, cwd):
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        self.assertEqual(proc.returncode, 0, (proc.stdout+proc.stderr)[-3500:])
        return proc.stdout

    def assert_output(self, pdf, meta, include_ai=True):
        result = CHECK.verify(pdf, meta, expected_year=2027)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["summary_last_page"], 1)
        self.assertEqual(result["solution_pages"], 5)
        self.assertEqual(result["ai_report_pages"], 2 if include_ai else 0)
        with fitz.open(pdf) as document:
            self.assertEqual(len(document), 7 if include_ai else 5)
            contents = CHECK.normalized(document[1].get_text())
            self.assertIn("Model", contents)
            self.assertIn("Results", contents)
            self.assertIn("Letter to a Fictional Agency", contents)
            self.assertNotIn("Report on Use of AI Tools", contents)

    @unittest.skipUnless(LATEX, "XeLaTeX unavailable; compiler check not executed")
    def test_latex_compiles_and_exports_real_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/"latex"
            PREPARE.prepare("latex", folder)
            (folder/"build").mkdir()
            version = self.run_cmd([LATEX, "--version"], folder)
            flags = ["--disable-installer"] if "MiKTeX" in version else []
            for include_ai in (True, False):
                with self.subTest(include_ai=include_ai):
                    fill(folder, "latex", include_ai)
                    for _ in range(3):
                        self.run_cmd([LATEX, *flags, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "-output-directory=build", "main.tex"], folder)
                    self.assert_output(folder/"build/main.pdf", folder/"build/main.mcm.json", include_ai)

    @unittest.skipUnless(TYPST, "Typst unavailable; compiler check not executed")
    def test_typst_compiles_and_exports_real_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/"typst"
            PREPARE.prepare("typst", folder)
            (folder/"build").mkdir()
            help_text = subprocess.run([TYPST, "eval", "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            for include_ai in (True, False):
                with self.subTest(include_ai=include_ai):
                    fill(folder, "typst", include_ai)
                    self.run_cmd([TYPST, "compile", "main.typ", "build/main.pdf"], folder)
                    if help_text.returncode == 0:
                        data = self.run_cmd([TYPST, "eval", "query(<mcm-boundary>).first().value", "--in", "main.typ"], folder)
                    else:
                        data = self.run_cmd([TYPST, "query", "main.typ", "<mcm-boundary>", "--field", "value", "--one"], folder)
                    (folder/"build/main.mcm.json").write_text(data, encoding="utf-8")
                    self.assert_output(folder/"build/main.pdf", folder/"build/main.mcm.json", include_ai)
            (folder/"summary.typ").write_text(("Synthetic summary overflow must be detected. "*350), encoding="utf-8")
            self.run_cmd([TYPST, "compile", "main.typ", "build/main.pdf"], folder)
            if help_text.returncode == 0:
                data = self.run_cmd([TYPST, "eval", "query(<mcm-boundary>).first().value", "--in", "main.typ"], folder)
            else:
                data = self.run_cmd([TYPST, "query", "main.typ", "<mcm-boundary>", "--field", "value", "--one"], folder)
            (folder/"build/main.mcm.json").write_text(data, encoding="utf-8")
            result = CHECK.verify(folder/"build/main.pdf", folder/"build/main.mcm.json")
            self.assertFalse(result["passed"])
            self.assertGreater(result["summary_last_page"], 1)


if __name__ == "__main__":
    unittest.main()
