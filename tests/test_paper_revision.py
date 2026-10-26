import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check_paper_revision as revision
import check_paper_voice as voice


class PaperRevisionTests(unittest.TestCase):
    def compare(self,before,after,suffix='.md'):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/('a'+suffix),Path(directory)/('b'+suffix)
            a.write_text(before,encoding='utf-8');b.write_text(after,encoding='utf-8')
            return revision.compare(a,b)

    def analyze(self,source,suffix='.md',style=True):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/('paper'+suffix);file.write_text(source,encoding='utf-8')
            return voice.analyze([file],style_review=style)

    def test_anonymous_examples_keep_numbers_and_reject_real_changes(self):
        cases=json.loads((ROOT/'examples/paper-revision/cases.json').read_text(encoding='utf-8'))['cases']
        for case in cases:
            with self.subTest(case=case['id']):
                result=self.compare(case['before'],case['after'],case['format'])
                self.assertEqual(result['protected_passed'],case['expected_protected_passed'])
                if case.get('expected_claim_review'):self.assertTrue(result['claim_cues_changed'])
                self.assertFalse(result['semantic_equivalence_verified'])

    def test_style_candidates_are_optional_and_never_rewrites(self):
        source='一句话总结：该方法保留原约束。\n\n值得注意的是，需要核对比较条件。'
        old=self.analyze(source,style=False);new=self.analyze(source)
        self.assertFalse(old['review_required']);self.assertTrue(new['review_required'])
        self.assertTrue(new['passed']);self.assertEqual(new['error_count'],0)
        self.assertFalse(new['rewrites_text'])
        self.assertEqual({f['category'] for f in new['findings']},{'prompt-like-colon','paragraph-reference'})
        self.assertEqual({f['line'] for f in new['findings']},{1,3})

    def test_normal_numbers_headings_lists_and_quotes_are_not_style_defects(self):
        source='## 一、模型假设\n\n1. 保留必要步骤。\n2. 保留变量定义。\n\n> 一句话总结：这是被引用的原话。\n\n| 指标 | 值 |\n|---|---|\n| 参数 | 2 |\n\n首先计算残差，其次比较误差；数值收敛不能替代独立验证。'
        self.assertEqual(self.analyze(source)['findings'],[])

    def test_tex_math_code_and_comments_are_masked_for_style(self):
        source=r'\[\text{不是甲而是乙}\]'+'\n'+r'% 一句话总结：'+'\n'+r'\begin{verbatim}一句话总结：\end{verbatim}'+'\n正文保留真实结论。'
        self.assertEqual(self.analyze(source,'.tex')['findings'],[])

    def test_typst_comments_and_literals_retain_real_line_numbers(self):
        source='// 按你的要求\n/* 外层 /* 按你的要求 */ 注释 */\n#link("https://example.test/")[资料]\n\n按你的要求修改。'
        report=self.analyze(source,'.typ')
        self.assertEqual(report['error_count'],1);self.assertEqual(report['findings'][0]['line'],5)

    def test_scientific_contrast_is_review_only(self):
        report=self.analyze('这里不是因果效应，而是给定样本内的关联。')
        self.assertEqual(report['error_count'],0);self.assertTrue(report['review_required'])
        self.assertIn('必要比较保留',report['findings'][0]['reason'])

    def test_numeric_units_relations_and_equations_are_protected(self):
        for a,b,suffix in [('误差为10%。','误差为11%。','.md'),('延迟为10ms。','延迟为10s。','.md'),
                           ('p<0.05','p=0.05','.md'),('误差为−0.2。','误差为0.2。','.md'),
                           (r'\[y=x^2\]',r'\[y=x^3\]','.tex'),('$ y = x^2 $','$ y = x^3 $','.typ')]:
            with self.subTest(before=a,after=b):self.assertFalse(self.compare(a,b,suffix)['protected_passed'])

    def test_variable_type_and_domain_are_not_silently_relaxed(self):
        result=self.compare('变量x为非负整数。','变量x为实数。')
        self.assertIn('domain_terms_in_order',result['changed_protected_groups'])
        result=self.compare('变量范围待由实际模型给定。','变量范围为x≥0。')
        self.assertFalse(result['protected_passed'])

    def test_chinese_appendix_heading_without_space_is_protected(self):
        a='正文。\n\n## 附录一\n\n完整原件。'
        b='正文。\n\n## 附录一\n\n改过的原件。'
        self.assertIn('protected_tail',self.compare(a,b)['changed_protected_groups'])

    def test_citations_code_tables_and_appendix_are_protected(self):
        pairs=[(r'参考\cite{a2026}。',r'参考\cite{b2026}。','.tex'),
               ('```python\nx=1\n```','```python\nx=2\n```','.md'),
               ('|变量|说明|\n|---|---|\n|x|非负|','|变量|说明|\n|---|---|\n|x|正值|','.md'),
               ('正文。\n\\appendix\n保护原文。','正文。\n\\appendix\n已修改原文。','.tex')]
        for a,b,suffix in pairs:
            with self.subTest(before=a):self.assertFalse(self.compare(a,b,suffix)['protected_passed'])

    def test_ai_usage_disclosure_remains_exact(self):
        a='## AI工具使用声明\n\n本队使用工具审阅代码。'
        b='## AI工具使用声明\n\n本队未使用工具。'
        result=self.compare(a,b)
        self.assertIn('protected_tail',result['changed_protected_groups'])

    def test_claim_strength_change_requires_manual_review(self):
        result=self.compare('该结果可能与温度相关。','该结果证明温度造成变化。')
        self.assertTrue(result['protected_passed']);self.assertTrue(result['review_required'])
        self.assertTrue(result['claim_cues_changed']);self.assertFalse(result['scientific_verified'])

    def test_display_period_not_decimal_product_derivative_or_inline_sentence(self):
        source=r'\[x=1.25\].'+'\n'+r'\[a\cdot b+\dot{x}+\ldots\]'+'\n'+r'正文中的 $x=1$。'
        report=self.analyze(source,'.tex',style=False)
        self.assertEqual([f['category'] for f in report['findings']],['formula-ending-period'])
        self.assertEqual(report['findings'][0]['line'],1)
        self.assertEqual(self.analyze('$ x = 1.25 $ .','.typ',style=False)['findings'][0]['category'],'formula-ending-period')
        self.assertEqual(self.analyze(r'\[x=1 .\]','.tex',style=False)['findings'][0]['category'],'formula-ending-period')

    def test_equation_system_missing_domain_note_is_a_candidate_not_an_invented_bound(self):
        system=r'\[\begin{cases}x+y=1\\x-y=0\end{cases}\]'
        missing=self.analyze(system,'.tex',style=False)
        self.assertEqual(missing['findings'][0]['category'],'equation-domain-note')
        self.assertFalse(missing['equation_systems'][0]['variables_verified'])
        described=self.analyze(system+'\n其中，变量范围为 $x,y\\in\\mathbb{R}$。','.tex',style=False)
        self.assertEqual(described['findings'],[])
        self.assertTrue(described['equation_systems'][0]['domain_note_hint'])
        self.assertFalse(described['equation_systems'][0]['variables_verified'])

    def test_typst_system_domain_note_and_comment_exclusion(self):
        system='$ cases(x + y = 1, x - y = 0) $'
        self.assertEqual(self.analyze(system,'.typ',style=False)['findings'][0]['category'],'equation-domain-note')
        self.assertFalse(self.analyze(system+'\n其中，x,y取值为实数。','.typ',style=False)['findings'])
        self.assertEqual(self.analyze('```tex\n'+system+'\n```','.md')['findings'],[])

    def test_cli_is_read_only_and_errors_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a.md',Path(directory)/'b.md'
            a.write_text('误差为10%。',encoding='utf-8');b.write_text('误差为11%。',encoding='utf-8')
            before={p.name:p.read_bytes() for p in Path(directory).iterdir()}
            run=subprocess.run([sys.executable,str(ROOT/'scripts/check_paper_revision.py'),str(a),str(b),'--json'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(run.returncode,1,run.stderr);self.assertFalse(json.loads(run.stdout)['protected_passed'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(directory).iterdir()})
            run=subprocess.run([sys.executable,str(ROOT/'scripts/check_paper_revision.py'),str(a),str(b.with_suffix('.pdf')),'--json'],capture_output=True)
            self.assertEqual(run.returncode,2)


if __name__=='__main__':unittest.main()
