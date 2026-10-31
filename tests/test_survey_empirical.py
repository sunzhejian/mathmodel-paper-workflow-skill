"""Offline, deliberately small regression cases; these are not study responses."""
import copy,importlib.util,json,math,sys,tempfile,unittest
from pathlib import Path
from scipy.stats import chi2_contingency
spec=importlib.util.spec_from_file_location('empirical',Path(__file__).resolve().parents[1]/'scripts/survey_empirical.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture():
    q={'title':'Offline regression fixture','questions':[
        {'id':'Y','type':'single','options':[{'id':'yes','label':'是'},{'id':'no','label':'否'}]},
        {'id':'X','type':'single','options':[{'id':'a','label':'甲'},{'id':'b','label':'乙'}]},
        {'id':'M','type':'multiple','minSelections':0,'options':[{'id':'one','label':'选项一'},{'id':'two','label':'选项二'}]}],
        'dimensions':[{'id':'region','values':[{'id':'north'},{'id':'south'}]}]}
    rows=[{'id':str(i),'source':'human_reported','traits':{'region':'north'if i<12 else'south'},'answers':{'Y':'yes'if i%3==0 else'no','X':'a'if i%2==0 else'b','M':['one']if i%4==0 else[]}}for i in range(24)]
    d={'source':'human_reported','records':rows}
    p={'outcome':{'question':'Y','positive':['yes'],'negative':['no']},'groups':['region'],'multiple':['M'],'cooccurrence':['M'],'resamples':999,'seed':713}
    return q,d,p

class Regression(unittest.TestCase):
    def test_group_missing_uses_actual_paired_cohort(self):
        q,d,p=fixture()
        for i in [0,1,12,13]:d['records'][i]['traits'].pop('region')
        result=m.tables(q,d,p)['group_permutation'][0]
        self.assertEqual(result['n'],20);self.assertEqual(result['excluded_group_missing'],4)
        observed=[[sum(r['traits'].get('region')==g and r['answers']['Y']==y for r in d['records'])for y in ['yes','no']]for g in ['north','south']]
        self.assertAlmostEqual(result['chi2'],chi2_contingency(observed,correction=False).statistic,places=12)
        self.assertEqual(result['events'],6);self.assertEqual(result['status'],'estimated')
    def test_multiple_one_outcome_has_no_response(self):
        q,d,p=fixture()
        for r in d['records']:
            if r['answers']['Y']=='yes':r['answers'].pop('M')
        rows=m.tables(q,d,p)['multiple_contrasts']
        self.assertEqual(len(rows),2)
        for r in rows:self.assertEqual(r['paid_n'],0);self.assertIsNone(r['paid_pct']);self.assertIsNone(r['p']);self.assertEqual(r['family_tests'],0)
    def test_allowed_empty_multiple_is_a_valid_zero_selection(self):
        q,d,p=fixture();a=m.tables(q,d,p)
        row=next(r for r in a['measurement_profile']if r['question']=='M')
        self.assertEqual(row['valid_n'],24);self.assertEqual(row['missing'],0)
        self.assertEqual(a['cooccurrence'][0]['n'],24)
    def test_nonempty_multiple_requirement_preserves_missing(self):
        q,d,p=fixture();q['questions'][-1]['minSelections']=1;a=m.tables(q,d,p)
        row=next(r for r in a['measurement_profile']if r['question']=='M')
        self.assertEqual(row['valid_n'],6);self.assertEqual(row['missing'],18)
        self.assertEqual(a['cooccurrence'][0]['n'],6)
    def test_group_without_both_outcomes_keeps_descriptive_status(self):
        q,d,p=fixture()
        for r in d['records']:
            if r['answers']['Y']=='yes':r['traits'].pop('region')
        a=m.tables(q,d,p)['group_permutation'][0]
        self.assertEqual(a['n'],16);self.assertEqual(a['status'],'constant_outcome');self.assertIsNone(a['p'])
    def test_unknown_group_code_is_not_silently_dropped(self):
        q,d,p=fixture();d['records'][0]['traits']['region']='typo'
        with self.assertRaisesRegex(ValueError,'trait|dimension'):m.tables(q,d,p)
    def test_duplicate_questions_and_invalid_ordinal_plan_are_rejected(self):
        q,d,p=fixture();q['questions'].append(copy.deepcopy(q['questions'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):m.tables(q,d,p)
        q,d,p=fixture();p['ordinal']={'X':['a']}
        with self.assertRaisesRegex(ValueError,'Ordinal'):m.tables(q,d,p)
    def test_branch_conditions_match_editor_and_reject_hidden_answers(self):
        q,d,p=fixture();p['multiple']=[];p['cooccurrence']=[];q['questions'][-1]['showIf']={'all':[{'questionId':'X','operator':'neq','value':'b'},{'not':{'questionId':'Y','operator':'in','value':['no']}}]}
        for r in d['records']:
            if not(r['answers']['X']=='a'and r['answers']['Y']=='yes'):r['answers'].pop('M')
        a=m.tables(q,d,p);self.assertEqual(next(r for r in a['measurement_profile']if r['question']=='M')['structural_skip'],20)
        d['records'][1]['answers']['M']=['one']
        with self.assertRaisesRegex(ValueError,'outside declared branch'):m.tables(q,d,p)
    def test_outcome_leakage_inside_composite_condition_is_rejected(self):
        q,d,p=fixture();q['questions'][-1]['showIf']={'any':[{'questionId':'Y','operator':'eq','value':'yes'},{'questionId':'X','operator':'eq','value':'a'}]}
        for r in d['records']:
            if not(r['answers']['Y']=='yes'or r['answers']['X']=='a'):r['answers'].pop('M')
        with self.assertRaisesRegex(ValueError,'outcome-conditioned'):m.tables(q,d,p)
    def test_all_editor_operators_and_hidden_negative_parent(self):
        for op,value,expected in [('eq','a',12),('neq','b',12),('in',['a'],12),('notIn',['a'],12),('answered',None,24)]:
            q,d,p=fixture();p['multiple']=[];p['cooccurrence']=[];q['questions'][-1]['showIf']={'questionId':'X','operator':op,'value':value}
            for r in d['records']:
                visible=op=='answered'or(r['answers']['X']=='a'if op in ['eq','neq','in']else r['answers']['X']=='b')
                if not visible:r['answers'].pop('M')
            row=next(r for r in m.tables(q,d,p)['measurement_profile']if r['question']=='M');self.assertEqual(row['applicable_n'],expected)
        q,d,p=fixture();q['questions'].append({'id':'T','type':'text','showIf':{'questionId':'M','operator':'contains','value':'one'}})
        self.assertEqual(next(r for r in m.tables(q,d,p)['measurement_profile']if r['question']=='T')['applicable_n'],6)
        q,d,p=fixture();p['multiple']=[];p['cooccurrence']=[];q['questions'][1]['showIf']={'questionId':'Y','operator':'eq','value':'yes'};q['questions'][-1]['showIf']={'not':{'questionId':'X','operator':'eq','value':'b'}}
        for r in d['records']:
            if r['answers']['Y']=='no':r['answers'].pop('X')
            if r['answers'].get('X')!='a':r['answers'].pop('M')
        self.assertEqual(next(r for r in m.tables(q,d,p)['measurement_profile']if r['question']=='M')['applicable_n'],4)
    def test_large_rank_replay_is_deterministic_with_bounded_batches(self):
        q,d,p=fixture();q['questions'].append({'id':'Z','type':'single','options':[{'id':'lo'},{'id':'hi'}]});p.update({'groups':[],'multiple':[],'cooccurrence':[],'ordinal':{'X':['a','b'],'Z':['lo','hi']},'rank_pairs':[['X','Z']]})
        originals=d['records'];d['records']=[{**copy.deepcopy(originals[i%24]),'id':str(i)}for i in range(2100)]
        for i,r in enumerate(d['records']):r['answers']['Z']='hi'if i%5<2 else'lo'
        first=m.tables(q,d,p)['rank_permutation'][0];second=m.tables(q,d,p)['rank_permutation'][0];self.assertEqual(first,second);self.assertEqual(first['n'],2100)
    def test_cycles_and_fractional_resampling_are_rejected(self):
        q,d,p=fixture();q['questions'][0]['showIf']={'questionId':'X','operator':'answered'};q['questions'][1]['showIf']={'questionId':'Y','operator':'answered'}
        with self.assertRaisesRegex(ValueError,'Cyclic'):m.tables(q,d,p)
        q,d,p=fixture();p['resamples']=999.5
        with self.assertRaisesRegex(ValueError,'integer'):m.tables(q,d,p)
    def test_summary_and_manifest_bind_real_tables(self):
        q,d,p=fixture()
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);files=[]
            for name,value in [('questionnaire',q),('data',d),('plan',p)]:
                f=root/(name+'.json');f.write_text(json.dumps(value),encoding='utf8');files.append(f)
            out=root/'results';m.run(*files,out)
            report=(out/'summary.md').read_text(encoding='utf8');manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'))
            self.assertIn('24',report);self.assertIn('measurement_profile.csv',report);self.assertIn('Fisher',report)
            self.assertTrue(any(f['path']=='summary.md'for f in manifest['files']))
            self.assertEqual(manifest['analysis_unit'],'one_record_per_response')
            old=(out/'results.json').read_bytes();m.run(*files,out,overwrite=True);self.assertEqual((out/'results.json').read_bytes(),old)
            (out/'summary.md').write_text('human edit',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'edited'):m.run(*files,out,overwrite=True)

if __name__=='__main__':unittest.main()
