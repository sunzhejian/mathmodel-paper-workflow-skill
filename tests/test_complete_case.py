import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('case_reference',ROOT/'scripts/complete_case_reference.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)

class CompleteCaseTests(unittest.TestCase):
    def test_seasonal_start_and_repeat(self):
        pred,_=ref.forecast('seasonal_naive',np.arange(1,11),np.arange(1,11),np.arange(11,25))
        np.testing.assert_array_equal(pred,np.tile(np.arange(4,11),2))
    def test_weekly_model_recovers_noiseless_coefficients(self):
        t=np.arange(1,51);c=np.array([70,.18,12,6]);y=ref.features(t,True)@c
        p,fit=ref.forecast('trend_weekly',t,y,np.array([51,52]))
        np.testing.assert_allclose(fit,c,atol=1e-10)
        np.testing.assert_allclose(p,ref.features(np.array([51,52]),True)@c)
    def test_zero_and_capacity_boundary(self):
        self.assertEqual(ref.fleet(0)[:2],(0,0));self.assertEqual(ref.fleet(22)[:2],(1,0))
        self.assertEqual(ref.fleet(272)[:2],(6,4))
        with self.assertRaises(ValueError):ref.fleet(272.001)
    def test_fleet_cost_is_minimum_of_all_feasible_pairs(self):
        for q in [1,22,22.001,35,44,57,70,100,127.5,272]:
            for cp in [0,.2,.5]:
                a,b,_=ref.fleet(q,cp)
                costs=[1100*x+1800*z+cp*(45*x+65*z) for x in range(7) for z in range(5) if 22*x+35*z+1e-9>=q]
                self.assertAlmostEqual(1100*a+1800*b+cp*(45*a+65*b),min(costs))
    def test_stock_conservation_and_fill_rate(self):
        r,rows=ref.simulate([1,2],np.array([12,20]),np.array([10,10]),5)
        self.assertAlmostEqual(rows[0]['inventory'],3)
        self.assertAlmostEqual(rows[1]['shortage'],5)
        self.assertAlmostEqual(r['fill_rate'],27/32)
        self.assertAlmostEqual(r['total_cost'],sum(r[k] for k in ['fleet_cost','carbon_cost','holding_cost','shortage_cost']))
    def test_bias_sign_and_mae(self):
        self.assertEqual(ref.metrics(np.array([3.,5.]),np.array([1.,3.])),{'rmse':2.,'mae':2.,'bias':2.})
    def test_robust_regrets_have_zero_row_minima(self):
        _,s,_,regret=ref.select([1,2],np.array([12,20]),np.array([10,10]),[0,5,10],[.9,1,1.1])
        self.assertTrue((regret>=-1e-8).all());np.testing.assert_allclose(regret.min(axis=1),0)
        self.assertIn(s,[0,5,10])
    def test_unsupported_contract_is_not_graded_against_hidden_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'case.json').write_text(json.dumps({'schema_version':1,'training_end':60}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Unsupported case parameters'):ref.solve(root)

if __name__=='__main__':unittest.main()
