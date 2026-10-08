import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/ctex_fontset_guard.py"
SPEC = importlib.util.spec_from_file_location("ctex_fontset_guard", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FontsetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "main.tex"
        self.output = self.root / "main-new.tex"

    def write(self, content):
        self.source.write_bytes(content.encode("utf-8"))

    def test_first_comment_match_cannot_mask_actual_mac_declaration(self):
        text = "% 默认fontset=mac\n% 改fontset=mac为windows\n\\documentclass[fontset=mac,12pt]{ctexart}\n\\begin{document}中文\\end{document}\n"
        self.write(text)
        self.assertEqual(m.inspect(self.source, "windows")["status"], "declaration_mismatch")
        report = m.adapt(self.source, "windows", self.output)
        actual = self.output.read_text(encoding="utf-8")
        self.assertIn("% 默认fontset=mac", actual)
        self.assertIn(r"\documentclass[fontset=windows,12pt]{ctexart}", actual)
        self.assertEqual(self.source.read_bytes(), text.encode("utf-8"))
        self.assertTrue(report["source_input_preserved"])
        self.assertEqual(report["compilation"], "not_run")

    def test_incorrect_first_string_replacement_still_reports_mismatch(self):
        self.write("% fontset=windows\n\\documentclass[fontset=mac]{ctexart}\n")
        self.assertEqual(m.inspect(self.source, "windows")["fontset"], "mac")

    def test_multiline_comments_bom_and_crlf_preserved_except_value(self):
        text = "\ufeff% fontset=mac\r\n\\documentclass[12pt,\r\n % 参数说明\r\n fontset = {mac}, a4paper]{ctexbook}\r\n"
        self.write(text)
        m.adapt(self.source, "linux", self.output)
        self.assertEqual(self.output.read_bytes(), text.replace("{mac}", "fandol").encode("utf-8"))

    def test_all_platform_strategies(self):
        for platform, value in m.STRATEGIES.items():
            with self.subTest(platform=platform):
                self.write("\\documentclass[fontset=" + value + "]{ctexrep}\n")
                self.assertEqual(m.inspect(self.source, platform)["status"], "declaration_matches_strategy")

    def test_escaped_percent_does_not_start_a_comment(self):
        text = r"\newcommand{\percent}{\%}" + "\n" + r"\documentclass[fontset=mac]{ctexart}"
        self.write(text)
        self.assertEqual(m.inspect(self.source, "macos")["status"], "declaration_matches_strategy")

    def test_body_documentclass_example_not_used(self):
        self.write("\\documentclass[fontset=windows]{ctexart}\n\\begin{document}\n\\verb|\\documentclass[fontset=mac]{ctexart}|\n")
        self.assertEqual(m.inspect(self.source, "windows")["fontset"], "windows")

    def test_commented_fake_documentclass_not_used(self):
        self.write("% \\documentclass[fontset=windows]{ctexart}\n\\documentclass[fontset=mac]{ctexart}")
        self.assertEqual(m.inspect(self.source, "windows")["declaration_line"], 2)

    def test_ambiguous_macro_or_forwarded_configuration_refused(self):
        cases = [r"\documentclass[fontset=mac]{ctexart}\documentclass[fontset=windows]{ctexart}",
                 r"\documentclass[fontset=mac,fontset=windows]{ctexart}",
                 r"\documentclass[fontset=\MyFonts]{ctexart}",
                 r"\newcommand{\load}{\documentclass[fontset=mac]{ctexart}}",
                 r"\PassOptionsToClass{fontset=windows}{ctexart}\documentclass[fontset=mac]{ctexart}"]
        for text in cases:
            with self.subTest(text=text):
                self.write(text)
                self.assertEqual(m.inspect(self.source, "windows")["status"], "review_required")
                with self.assertRaises(ValueError):m.adapt(self.source, "windows", self.output)
                self.assertFalse(self.output.exists())

    def test_custom_fontsets_none_or_absent_are_not_overridden(self):
        for option in ("fontset=none", "fontset=adobe", "12pt"):
            with self.subTest(option=option):
                self.write("\\documentclass["+option+"]{ctexart}")
                self.assertEqual(m.inspect(self.source, "windows")["status"], "review_required")

    def test_nonctex_class_and_ctex_package_boundaries(self):
        self.write(r"\documentclass{article}")
        self.assertEqual(m.inspect(self.source, "windows")["status"], "not_applicable")
        self.write(r"\documentclass{article}\usepackage[fontset=mac]{ctex}")
        self.assertEqual(m.inspect(self.source, "windows")["status"], "review_required")

    def test_no_overwrite_input_or_existing_paper(self):
        self.write(r"\documentclass[fontset=mac]{ctexart}")
        with self.assertRaises(ValueError):m.adapt(self.source, "windows", self.source)
        self.output.write_text("existing user's paper", encoding="utf-8")
        with self.assertRaises(ValueError):m.adapt(self.source, "windows", self.output)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing user's paper")

    def test_cli_inspect_has_actionable_exit_code_without_editing(self):
        self.write(r"\documentclass[fontset=mac]{ctexart}")
        before = self.source.read_bytes()
        p = subprocess.run([sys.executable, str(PATH), "inspect", str(self.source), "--platform", "windows"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["fontset"], "mac")
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
