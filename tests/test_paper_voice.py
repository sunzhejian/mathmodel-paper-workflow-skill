import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_paper_voice.py"
SPEC = importlib.util.spec_from_file_location("check_paper_voice", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PaperVoiceTests(unittest.TestCase):
    def analyze_text(self, source, suffix=".tex", **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / ("paper" + suffix)
            page.write_text(source, encoding="utf-8")
            return MODULE.analyze([page], **kwargs)

    def test_caption_instruction_is_flagged_but_latex_comment_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "paper.tex"
            page.write_text(r"\caption{主要符号说明（一行一符号）}" + "\n" +
                            r"% 用户指定" + "\n", encoding="utf-8")
            result = MODULE.inspect([page])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["phrase"], "一行一符号")

    def test_normal_method_and_ai_statement_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "paper.tex"
            page.write_text(r"\caption{主要符号说明}" + "\n" +
                            "本参赛队在竞赛过程中使用了 AI 工具，用于模型推导与审查。\n",
                            encoding="utf-8")
            self.assertEqual(MODULE.inspect([page]), [])

    def test_emphasis_and_scientific_defense_are_not_banned(self):
        snippets = [
            r"\textbf{关键结果为 $t_*=10\,\mathrm{h}$}。",
            r"\boxed{\partial_t C=D\Delta C},\quad D>0",
            "值得注意的是，残差较小不能替代独立数据检验。",
            "结果不代表模型在任意温度下都成立，适用范围由标定数据限定。",
            "与常系数假设不同，扩散系数随含水率更新。",
            "需要指出，现有观测仅能限制参数区间，无法辨识唯一数值。",
            "试运行采用用户指定的负荷，按用户要求比较两种运行方案。",
            "本研究根据赛题附录给出的物性关系确定参数。",
            "Under these conditions, the results suggest a change in the ranking; uncertainty remains.",
            "The model is not identifiable from these observations alone.",
        ]
        for source in snippets:
            with self.subTest(source=source):
                report = self.analyze_text(source)
                self.assertTrue(report["passed"])
                self.assertFalse(report["review_required"])
                self.assertEqual(report["findings"], [])

    def test_wrapped_instruction_keeps_real_source_line(self):
        report = self.analyze_text("主要结果如下。\n按你的\n要求，输出新的图形。\n")
        self.assertFalse(report["passed"])
        self.assertEqual(report["findings"][0]["line"], 2)
        self.assertEqual(report["findings"][0]["phrase"], "按你的要求")

    def test_internal_notes_are_review_candidates_and_public_code_is_allowed(self):
        report = self.analyze_text("根据 RESULTS_REPORT.md 确定答案。\n"
                                   r"\texttt{reports/check.json} 说明论文已通过全部检查。" + "\n"
                                   "复现代码 solve_q1.py 实现有限体积离散。\n")
        self.assertTrue(report["passed"])
        self.assertTrue(report["review_required"])
        self.assertEqual(report["review_count"], 3)
        self.assertEqual({f["line"] for f in report["findings"]}, {1, 2})

    def test_tex_comments_percent_and_code_do_not_mask_real_prose(self):
        source = (r"误差为 2\%。 % 按你的要求" + "\n"
                  r"换行\\% 按你的要求" + "\n"
                  r"% \begin{verbatim} 按你的要求" + "\n"
                  r"\begin{verbatim}% 按你的要求\end{verbatim}" + "\n"
                  r"\begin{lstlisting}" + "\n按你的要求\n" + r"\end{lstlisting}" + "\n"
                  r"\caption{按你的要求修图}" + "\n")
        report = self.analyze_text(source)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["findings"][0]["line"], 8)

    def test_artifact_at_line_start_has_its_own_line_number(self):
        report = self.analyze_text("检验说明。\n\nreports/grid-check.json 已完成。\n", ".md")
        self.assertEqual(report["review_count"], 1)
        self.assertEqual(report["findings"][0]["line"], 3)
        self.assertEqual(report["findings"][0]["phrase"], "reports/grid-check.json")

    def test_markdown_code_comments_and_inline_prose_have_distinct_roles(self):
        source = ("<!-- 按你的要求\n我已经编译 -->\n"
                  "````text\n按你的要求\n```\n我已经编译\n````\n"
                  "~~~python\nprint('按你的要求')\n~~~\n"
                  "根据 `RESULTS_REPORT.md` 写结论。\n"
                  "按你的要求，重新作图。\n")
        report = self.analyze_text(source, ".md")
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["review_count"], 1)
        self.assertEqual([f["line"] for f in report["findings"]], [11, 12])

    def test_html_comment_token_inside_code_cannot_hide_later_body(self):
        source = "```html\n<!-- 按你的要求\n```\n按你的要求修改。\n"
        report = self.analyze_text(source, ".md")
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["findings"][0]["line"], 4)

    def test_appendix_boundary_is_explicit_and_comments_are_not_boundaries(self):
        source = (r"% \appendix" + "\n按你的要求改写。\n" +
                  r"\appendix" + "\n我已经编译。\n")
        self.assertEqual(self.analyze_text(source)["error_count"], 2)
        report = self.analyze_text(source, stop_at_appendix=True)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["findings"][0]["line"], 2)

    def test_explicit_exclusions_and_overlapping_inputs_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "body.tex").write_text("模型与结果。", encoding="utf-8")
            appendix = root / "appendix"
            appendix.mkdir()
            page = appendix / "old.tex"
            page.write_text("按你的要求。", encoding="utf-8")
            report = MODULE.analyze([root, page], exclude=("appendix/*",))
            self.assertTrue(report["passed"])
            self.assertEqual(len(report["checked_files"]), 1)
            self.assertEqual(report["excluded_files"], [str(page.resolve())])
            self.assertEqual(page.read_text(encoding="utf-8"), "按你的要求。")

    def test_english_assistant_leak_but_actual_ai_disclosure_is_retained(self):
        report = self.analyze_text("We used an AI language model to review the code.\n"
                                   "As an AI language model, I cannot run the simulation.\n", ".md")
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["findings"][0]["line"], 2)

    def test_cli_json_distinguishes_review_from_error_and_empty_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "body.md"
            for content, expected_code, expected_errors, expected_reviews in [
                ("正文依据 RESULTS_REPORT.md。", 0, 0, 1),
                ("按你的要求，模型已修改。", 1, 1, 0),
            ]:
                with self.subTest(content=content):
                    page.write_text(content, encoding="utf-8")
                    run = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), str(page), "--json"],
                                         capture_output=True, text=True, encoding="utf-8")
                    report = json.loads(run.stdout)
                    self.assertEqual(run.returncode, expected_code, run.stderr)
                    self.assertEqual(report["error_count"], expected_errors)
                    self.assertEqual(report["review_count"], expected_reviews)
            empty = root / "empty"
            empty.mkdir()
            run = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), str(empty), "--json"], capture_output=True)
            self.assertEqual(run.returncode, 2)

    def test_pdf_and_missing_source_are_not_reported_as_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "paper.pdf"
            page.write_bytes(b"fake PDF fixture")
            with self.assertRaises(ValueError):
                MODULE.analyze([page])
            with self.assertRaises(FileNotFoundError):
                MODULE.analyze([Path(tmp) / "missing.tex"])


if __name__ == "__main__":
    unittest.main()
