import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('trial_latex',ROOT/'scripts/check_trial_latex.py')
latex=importlib.util.module_from_spec(spec)
spec.loader.exec_module(latex)


class TrialLatexTests(unittest.TestCase):
    def test_long_line_warning_is_not_compile_success(self):
        result=latex.log_checks('Overfull \\hbox (84.15387pt too wide) detected at line 4\nOutput written on formulas.pdf')
        self.assertEqual(len(result['overfull']),1)
        self.assertIn('84.15387',result['overfull'][0])

    def test_missing_characters_and_undefined_commands_are_reported(self):
        result=latex.log_checks('Missing character: There is no X\n! Undefined control sequence.')
        self.assertTrue(result['missing_characters'])
        self.assertTrue(result['undefined_control_sequence'])

    def test_math_mode_error_is_preserved_for_repair(self):
        result=latex.log_checks('! Missing $ inserted.\nl.74 always_wins')
        self.assertEqual(result['latex_errors'],['! Missing $ inserted.'])

    def test_io_and_document_preambles_are_not_accepted_as_body(self):
        for fragment in [r'\input{secret}',r'\write18{command}',r'\csname input\endcsname',r'\documentclass{article}']:
            with self.assertRaises(ValueError):latex.body_source({'transport':{'latex_model':fragment},'inference':{'latex_model':r'\[x=1\]'}},2.5)


if __name__=='__main__':unittest.main()
