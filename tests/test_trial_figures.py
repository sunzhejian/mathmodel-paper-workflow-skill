import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trial_figures',ROOT/'scripts/generate_trial_figures.py')
figure=importlib.util.module_from_spec(spec)
spec.loader.exec_module(figure)


class TrialFigureMetrics(unittest.TestCase):
    def test_duplicate_reports_and_equivalent_fractions_are_one_input(self):
        a={'arguments':[37,20,9000,10000],'cost_expression':'900','matches_reference':True}
        b={**a,'cost_expression':'900/1','round':'another_label'}
        result=figure.distinct_cases({'a':{'source_sha256':'same','cases':[a]},'b':{'source_sha256':'same','cases':[b]}},['a','b'])
        self.assertEqual(result,{'passed':1,'total':1})

    def test_different_program_versions_are_not_combined(self):
        with self.assertRaises(ValueError):figure.distinct_cases({'a':{'source_sha256':'old','cases':[]},'b':{'source_sha256':'new','cases':[]}},['a','b'])

    def test_historical_evidence_has_13_unique_inputs_and_a_paired_comparison(self):
        data=figure.summarize(json.loads(figure.DEFAULT_EVIDENCE.read_text(encoding='utf-8')))
        self.assertEqual([m['code']['total'] for m in data['models']],[13,13,13])
        self.assertEqual(data['repair']['before'],{'passed':8,'total':11})
        self.assertEqual(data['repair']['after_same_inputs'],{'passed':11,'total':11})
        self.assertEqual(data['repair']['new_inputs'],{'passed':2,'total':2})


if __name__=='__main__':unittest.main()
