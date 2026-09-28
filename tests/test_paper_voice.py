import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_paper_voice.py"
SPEC = importlib.util.spec_from_file_location("check_paper_voice", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PaperVoiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
