import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('trial_code',ROOT/'scripts/check_trial_code.py')
code=importlib.util.module_from_spec(spec)
spec.loader.exec_module(code)


class TrialCodeTests(unittest.TestCase):
    def test_literal_backslash_n_is_not_silently_changed_into_program_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            answer=root/'answer.json'
            source='import math\\n'
            answer.write_text(json.dumps({'transport':{'solver_source':source}}),encoding='utf-8')
            report=code.execute(answer,ROOT/'examples/model-trials/tasks-v2.json',root/'run')
            self.assertFalse(report['execution_performed'])
            self.assertIn('syntax_error',report)
            self.assertEqual((root/'run/solver.py').read_text(),source)

    def test_fraction_outputs_are_valid_numeric_solver_results(self):
        source='''from fractions import Fraction
from math import ceil
def solve_transport(demand_tonnes,elevator_capacity_tonnes,rocket_capacity_kg,rocket_cost,cost_per_tonne):
    D=Fraction(demand_tonnes); E=Fraction(elevator_capacity_tonnes); r=Fraction(rocket_capacity_kg,1000)
    plans=[{'e_tonnes':max(Fraction(0),D-n*r),'launches':n,'cost':max(Fraction(0),D-n*r)*cost_per_tonne+n*rocket_cost} for n in range(ceil(max(0,D-E)/r),ceil(D/r)+1)]
    best=min(x['cost'] for x in plans)
    return [x for x in plans if x['cost']==best]
'''
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            answer=root/'answer.json'
            answer.write_text(json.dumps({'transport':{'solver_source':source}}),encoding='utf-8')
            report=code.execute(answer,ROOT/'examples/model-trials/tasks-v2.json',root/'run')
            self.assertEqual(report['passed'],8)
            self.assertTrue(report['all_checked_cases_pass'])


if __name__=='__main__':unittest.main()
