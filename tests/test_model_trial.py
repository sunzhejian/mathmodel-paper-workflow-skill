import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('model_trial',ROOT/'scripts/model_trial.py')
trial=importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class ModelTrialTests(unittest.TestCase):
    def test_nominal_and_changed_recommendation(self):
        d=json.loads(trial.TASKS.read_text())['rounds']['baseline']['transport']
        self.assertEqual(trial.optimal_plans(d,900),[{'e_tonnes':14,'launches':2,'cost':28600}])
        self.assertEqual(trial.optimal_plans(d,1100),[{'e_tonnes':6,'launches':3,'cost':30600}])

    def test_holdout_has_three_tied_plans(self):
        d=json.loads(trial.TASKS.read_text())['rounds']['holdout']['transport']
        switches=trial.switch_values(d)
        self.assertEqual(len(switches),1)
        self.assertAlmostEqual(switches[0],10000/9)
        self.assertEqual([p['launches'] for p in trial.optimal_plans(d,switches[0])],[2,3,4])
        self.assertEqual(trial.optimal_plans(d,1400),[{'e_tonnes':1,'launches':4,'cost':41400}])

    def test_unit_error_duplicates_and_boolean_values_are_rejected(self):
        expected=[{'e_tonnes':14,'launches':2,'cost':28600}]
        self.assertFalse(trial.plans_match([{'e_tonnes':14000,'launches':2,'cost':28600}],expected))
        self.assertFalse(trial.plans_match(expected+expected,expected))
        self.assertFalse(trial.plans_match([{'e_tonnes':14,'launches':True,'cost':28600}],expected))

    def test_prompt_contains_only_selected_case_and_no_reference_answers(self):
        text,manifest=trial.prompt('baseline')
        self.assertIn('"demand_tonnes": 30',text)
        self.assertNotIn('"demand_tonnes": 37',text)
        self.assertNotIn('28600',text)
        self.assertEqual(len(manifest['context_sha256']),3)

    def test_grade_missing_work_is_not_success(self):
        result=trial.grade({},'baseline')
        self.assertEqual(result['passed'],0)
        self.assertGreater(result['total'],0)

    def test_code_is_only_checked_for_presence_not_executed(self):
        result=trial.grade({'transport':{'solver_source':'raise RuntimeError("do not run")'}},'baseline')
        item=next(x for x in result['findings'] if x['check']=='transport_solver_source_present')
        self.assertTrue(item['passed'])
        self.assertIn('Code execution',result['limits'])

    def test_narrative_still_needs_review_when_numbers_pass(self):
        v=json.loads(trial.TASKS.read_text())['rounds']['baseline']['inference']
        p=(v['observed_combined_share_a']-v['judge_weight']*v['judge_share_a'])/(1-v['judge_weight'])
        i={'point_share_a':p,'rank_interval_a':{'lower':11/30,'upper':1,'lower_inclusive':False,'upper_inclusive':True},'absolute_votes_identifiable':False,'confidence_interval_available':False,'data_semantics':{'eliminated_zero':'structural zero','future_na':'not held'},'results_paragraph':'Contradictory prose is not automatically verified.','latex_model':'x=1'}
        result=trial.grade({'inference':i},'baseline')
        self.assertEqual(sum(x['passed'] for x in result['findings'] if x['check'] in ['exact_share','rank_identification_set','no_absolute_vote_claim','no_unsupported_confidence_interval']),4)
        self.assertIn('narrative agreement',result['limits'])

    def test_counting_convention_does_not_split_currency_or_hyphens(self):
        self.assertEqual(trial.word_count('A rate-sensitive plan costs 28,600 units — nominally.'),7)

    def test_invalid_json_is_recorded_and_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            answer=Path(temp)/'answer.txt'
            report=Path(temp)/'report.json'
            original='{"latex_model":"a\nb"}'
            answer.write_text(original,encoding='utf-8')
            result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/model_trial.py'),'grade','--round','baseline','--answer',str(answer),'--report',str(report)],capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,2)
            self.assertFalse(json.loads(report.read_text())['numeric_checks_executed'])
            self.assertEqual(answer.read_text(),original)

    def test_boolean_interval_endpoint_is_not_a_numeric_bound(self):
        result=trial.grade({'inference':{'rank_interval_a':{'lower':11/30,'upper':True,'lower_inclusive':False,'upper_inclusive':True}}},'baseline')
        item=next(x for x in result['findings'] if x['check']=='rank_identification_set')
        self.assertFalse(item['passed'])

    def test_wrong_rank_bound_has_an_original_score_counterexample(self):
        data=json.loads(trial.TASKS.read_text())['rounds']['holdout']['inference']
        proof=trial.rank_diagnostics(data,{'lower':0.5})
        self.assertAlmostEqual(proof['expected_lower'],0.65)
        self.assertAlmostEqual(proof['boundary_substitution']['combined_a'],proof['boundary_substitution']['combined_b'])
        witness=proof['counterexample']
        self.assertTrue(witness['inside_proposed_interval'])
        self.assertFalse(witness['original_ranking_holds'])

    def test_rank_sets_can_include_zero_or_be_empty(self):
        self.assertEqual(trial.expected_rank_interval({'judge_weight':0.8,'judge_share_a':0.9}),{'lower':0.0,'upper':1.0,'lower_inclusive':True,'upper_inclusive':True})
        self.assertIsNone(trial.expected_rank_interval({'judge_weight':0.7,'judge_share_a':0.2}))

    def test_exact_zero_and_one_ties_preserve_strictness(self):
        interval=trial.expected_rank_interval({'judge_weight':0.5,'judge_share_a':1})
        self.assertEqual(interval['lower'],0)
        self.assertFalse(interval['lower_inclusive'])
        self.assertIsNone(trial.expected_rank_interval({'judge_weight':0.5,'judge_share_a':0}))

    def test_judge_only_rank_does_not_divide_by_zero(self):
        self.assertTrue(trial.expected_rank_interval({'judge_weight':1,'judge_share_a':0.8})['lower_inclusive'])
        self.assertIsNone(trial.expected_rank_interval({'judge_weight':1,'judge_share_a':0.5}))

    def test_empty_rank_case_must_be_explicit_not_missing(self):
        path=ROOT/'examples/model-trials/tasks-v2.json'
        absent=trial.grade({},'clarified',path)
        self.assertFalse(next(x for x in absent['findings'] if x['check']=='rank_case_impossible_win')['passed'])
        explicit=trial.grade({'inference':{'rank_case_intervals':[{'case_id':'impossible_win','interval':None}]}},'clarified',path)
        self.assertTrue(next(x for x in explicit['findings'] if x['check']=='rank_case_impossible_win')['passed'])

    def test_split_prompt_only_contains_the_selected_task(self):
        text,manifest=trial.prompt('clarified',ROOT/'examples/model-trials/tasks-v2.json','inference')
        self.assertEqual(manifest['part'],'inference')
        self.assertIn('TASK inference:',text)
        self.assertNotIn('TASK transport:',text)
        self.assertNotIn('"demand_tonnes": 37',text)

    def test_written_prompt_matches_its_recorded_byte_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'prompt-stage'
            result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/model_trial.py'),'prepare','--round','baseline','--output',str(output)],capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0)
            manifest=json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['prompt_sha256'],hashlib.sha256((output/'prompt.txt').read_bytes()).hexdigest())

    def test_exact_fraction_encoding_is_scoped_and_does_not_evaluate_expressions(self):
        self.assertAlmostEqual(trial.numeric_value('10000/9',True),10000/9)
        for value in ['1/0','sum([1,2])','2**10','0.5',True]:
            with self.assertRaises(ValueError):trial.numeric_value(value,True)
        with self.assertRaises(ValueError):trial.numeric_value('10000/9',False)

    def test_rocket_only_switch_has_its_own_exact_price(self):
        from fractions import Fraction
        data={'demand_tonnes':30,'elevator_capacity_tonnes':18,'rocket_capacity_kg':8000,'rocket_cost':8000,'cost_range':[800,1500]}
        self.assertEqual(trial.exact_switch_values(data),[Fraction(1000),Fraction(4000,3)])

    def test_fractional_mass_at_capacity_is_feasible(self):
        data={'demand_tonnes':0.4,'elevator_capacity_tonnes':0.15,'rocket_capacity_kg':250,'rocket_cost':1}
        self.assertEqual(trial.optimal_plans(data,1),[{'e_tonnes':0.15,'launches':1,'cost':1.15}])


if __name__=='__main__': unittest.main()
