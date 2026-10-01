"""Prepare anonymous task prompts and grade numeric model outputs, without API calls.

This deliberately does not execute model-generated Python or TeX. Those artifacts
need human review and independent execution/compilation before being called verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / 'examples/model-trials/tasks.json'
CONTEXT_FILES = ['SKILL.md', 'references/evidence-and-writing.md', 'references/mcm-icm.md']


def optimal_plans(data: dict, c: float) -> list[dict]:
    capacity = Fraction(str(data['rocket_capacity_kg'])) / 1000
    demand=Fraction(str(data['demand_tonnes']))
    cap=Fraction(str(data['elevator_capacity_tonnes']))
    rate=Fraction(str(c))
    candidates = []
    for n in range(math.ceil(demand / capacity) + 1):
        e = max(0, demand - n * capacity)
        if e <= cap:
            candidates.append({'e_tonnes': float(e), 'launches': n,
                               'cost': float(n * data['rocket_cost'] + e * rate)})
    best = min(p['cost'] for p in candidates)
    return [p for p in candidates if math.isclose(p['cost'], best, rel_tol=1e-10, abs_tol=1e-7)]


def switch_values(data: dict) -> list[float]:
    return [float(c) for c in exact_switch_values(data)]


def exact_switch_values(data: dict) -> list[Fraction]:
    # Filter pairwise intersections by the exact lower envelope, including the
    # rocket-only plan whose remaining-load interval may have a different slope.
    capacity=Fraction(str(data['rocket_capacity_kg']))/1000
    demand=Fraction(str(data['demand_tonnes']))
    cap=Fraction(str(data['elevator_capacity_tonnes']))
    fixed=Fraction(str(data['rocket_cost']))
    candidates=[(n,max(0,demand-n*capacity)) for n in range(math.ceil(demand/capacity)+1) if max(0,demand-n*capacity)<=cap]
    result=set()
    for n,e in candidates:
        for m,f in candidates:
            if n>=m or e==f:continue
            c=(m-n)*fixed/(e-f)
            if not Fraction(str(data['cost_range'][0]))<=c<=Fraction(str(data['cost_range'][1])):continue
            costs=[k*fixed+mass*c for k,mass in candidates]
            if sum(cost==min(costs) for cost in costs)>1:result.add(c)
    return sorted(result)


def prompt(round_name: str, tasks_path: Path = TASKS, part: str = 'both') -> tuple[str, dict]:
    tasks = json.loads(tasks_path.read_text(encoding='utf-8'))
    data = tasks['rounds'][round_name]
    contexts, hashes = [], {}
    for filename in CONTEXT_FILES:
        raw = (ROOT / filename).read_bytes()
        hashes[filename] = hashlib.sha256(raw).hexdigest()
        contexts.append(f'\n--- {filename} ---\n{raw.decode("utf-8")}')
    response=tasks['response_request'] if part=='both' else f'Return exactly one valid JSON object with only the top-level key {part}. All task inputs and skill guidance are provided below. Do not call tools. Escape LaTeX backslashes and string newlines correctly; a TeX command uses one backslash after JSON decoding, not two. Do not claim code execution or compilation. Keep development/QA process information outside scientific paragraphs and letter. Deliver only the selected task; the complementary task is a separate stage.'
    text = response + '\n' + ''.join(contexts)
    selected=('transport','inference') if part=='both' else (part,)
    for kind in selected:
        text += f'\n\nTASK {kind}:\n{tasks[kind + "_request"]}\nINPUT DATA:\n{json.dumps(data[kind])}'
    manifest = {'round': round_name, 'part':part, 'task_schema_version':tasks.get('schema_version',1), 'task_sha256': hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
                'context_sha256': hashes, 'prompt_sha256': hashlib.sha256(text.encode()).hexdigest()}
    return text, manifest


def parse_answer(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError('Expected an object')
    return result


def numeric_value(value: object, allow_fraction: bool = False) -> float:
    if isinstance(value,bool):raise ValueError('Boolean is not a numeric value')
    if isinstance(value,(int,float)) and math.isfinite(value):return float(value)
    if allow_fraction and isinstance(value,str) and len(value)<=64 and re.fullmatch(r'[+-]?\d+/[1-9]\d*',value):
        return float(Fraction(value))
    raise ValueError('Unsupported scalar encoding')


def plans_match(got: object, expected: list[dict], allow_fraction: bool = False) -> bool:
    if not isinstance(got, list) or len(got) != len(expected):
        return False
    try:
        ordered = sorted(got, key=lambda x: x['launches'])
        expected = sorted(expected, key=lambda x: x['launches'])
        for a, b in zip(ordered, expected):
            for key in ('e_tonnes', 'launches', 'cost'):
                value = numeric_value(a[key],allow_fraction and key!='launches')
                if not math.isclose(value, b[key], rel_tol=1e-7, abs_tol=1e-6):
                    return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def word_count(text: object) -> int:
    # Declared English fixture convention: whitespace-delimited tokens containing
    # letters/digits. Punctuation-only tokens do not count; 28,600 counts once.
    return sum(bool(re.search(r'\w', token)) for token in text.split()) if isinstance(text,str) else 0


def expected_rank_interval(data: dict) -> dict | None:
    alpha=Fraction(str(data['judge_weight']))
    judge=Fraction(str(data['judge_share_a']))
    if not 0<=alpha<=1 or not 0<=judge<=1:
        raise ValueError('Weights and judge shares must lie in [0,1]')
    if alpha==1:
        return {'lower':0.0,'upper':1.0,'lower_inclusive':True,'upper_inclusive':True} if judge>Fraction(1,2) else None
    threshold=(1-alpha*(2*judge-1)/(1-alpha))/2
    if threshold>=1:return None
    return {'lower':float(max(0,threshold)),'upper':1.0,'lower_inclusive':threshold<0,'upper_inclusive':True}


def interval_matches(got: object, expected: dict | None) -> bool:
    if expected is None:return got is None
    if not isinstance(got,dict):return False
    try:
        for key in ['lower','upper']:
            if isinstance(got[key],bool) or not isinstance(got[key],(int,float)) or not math.isfinite(got[key]):return False
            if not math.isclose(got[key],expected[key],rel_tol=1e-7,abs_tol=1e-9):return False
        return all(got[key] is expected[key] for key in ['lower_inclusive','upper_inclusive'])
    except (KeyError,TypeError,ValueError):return False


def rank_diagnostics(data: dict, interval: object) -> dict:
    alpha=data['judge_weight']
    judge=data['judge_share_a']
    expected_set=expected_rank_interval(data)
    expected=(1-alpha*(2*judge-1)/(1-alpha))/2 if alpha!=1 else None
    def scores(p):
        return {'fan_share_a':p,'combined_a':alpha*judge+(1-alpha)*p,
                'combined_b':alpha*(1-judge)+(1-alpha)*(1-p)}
    result={'ranking_interpretation':'Combined score s_A > s_B, using the supplied weighting definition',
            'expected_interval':expected_set,'expected_lower':expected,
            'boundary_substitution':scores(expected) if expected is not None and 0<=expected<=1 else None,
            'endpoint_substitution':[scores(0),scores(1)]}
    got=interval.get('lower') if isinstance(interval,dict) else None
    if expected is not None and 0<=expected<=1 and not isinstance(got,bool) and isinstance(got,(int,float)) and math.isfinite(got) and 0<=got<=1 and not math.isclose(got,expected,abs_tol=1e-8):
        p=(got+expected)/2
        witness=scores(p)
        witness['inside_proposed_interval']=p>got
        witness['original_ranking_holds']=witness['combined_a']>witness['combined_b']
        result['counterexample']=witness
    return result


def grade(answer: dict, round_name: str, tasks_path: Path = TASKS) -> dict:
    task=json.loads(tasks_path.read_text(encoding='utf-8'))
    data = task['rounds'][round_name]
    allow_fraction=task.get('schema_version',1)>=2
    findings = []
    def check(name, passed, detail=''):
        findings.append({'check': name, 'passed': bool(passed), 'detail': detail})
    t = answer.get('transport', {})
    i = answer.get('inference', {})
    if not isinstance(t, dict): t = {}
    if not isinstance(i, dict): i = {}
    d = data['transport']
    check('nominal_optimum', plans_match(t.get('nominal_plans'), optimal_plans(d, d['nominal_cost_per_tonne']),allow_fraction))
    endpoints = t.get('endpoint_plans', [])
    for c in d['cost_range']:
        got = next((p.get('plans') for p in endpoints if isinstance(p, dict) and p.get('cost_per_tonne') == c), None) if isinstance(endpoints, list) else None
        check(f'endpoint_{c}', plans_match(got, optimal_plans(d, c),allow_fraction))
    expected = switch_values(d)
    got = t.get('switches', [])
    valid = isinstance(got, list) and len(got) == len(expected)
    if valid:
        try:
            got = sorted(got, key=lambda x:numeric_value(x['cost_per_tonne'],allow_fraction))
            valid = all(math.isclose(numeric_value(p['cost_per_tonne'],allow_fraction), c, rel_tol=1e-7) and plans_match(p['plans'], optimal_plans(d,c),allow_fraction) for p,c in zip(got,expected))
        except (KeyError, TypeError, ValueError): valid = False
    check('switches_and_all_ties', valid)
    for field, lo, hi in [('summary',70,110),('letter',130,190)]:
        count = word_count(t.get(field))
        check(field+'_length',lo <= count <= hi,f'{count} words; content needs separate review')
    for field in ['solver_source','latex_model','uncertainty_kind']:
        check('transport_'+field+'_present', isinstance(t.get(field),str) and bool(t[field].strip()))
    v = data['inference']
    p = (v['observed_combined_share_a'] - v['judge_weight'] * v['judge_share_a']) / (1-v['judge_weight'])
    point = i.get('point_share_a')
    check('exact_share',not isinstance(point,bool) and isinstance(point,(int,float)) and math.isfinite(point) and math.isclose(point,p,rel_tol=1e-7))
    interval = i.get('rank_interval_a', {})
    correct = interval_matches(interval,expected_rank_interval(v))
    check('rank_identification_set',correct)
    proposed=i.get('rank_case_intervals',[])
    for case in v.get('rank_cases',[]):
        matches=[x for x in proposed if isinstance(x,dict) and x.get('case_id')==case['case_id']] if isinstance(proposed,list) else []
        check('rank_case_'+case['case_id'],len(matches)==1 and 'interval' in matches[0] and interval_matches(matches[0]['interval'],expected_rank_interval(case)))
    check('no_absolute_vote_claim',i.get('absolute_votes_identifiable') is False)
    check('no_unsupported_confidence_interval',i.get('confidence_interval_available') is False)
    semantics=i.get('data_semantics',{})
    check('data_semantics_present',isinstance(semantics,dict) and all(isinstance(semantics.get(k),str) and semantics[k].strip() for k in ['eliminated_zero','future_na']))
    check('inference_paragraph_present',isinstance(i.get('results_paragraph'),str) and bool(i['results_paragraph'].strip()))
    check('inference_model_present',isinstance(i.get('latex_model'),str) and bool(i['latex_model'].strip()))
    return {'round':round_name,'passed':sum(x['passed'] for x in findings),'total':len(findings),'findings':findings,
            'rank_diagnostics':rank_diagnostics(v,interval),
            'limits':'Numeric/shape checks only. Code execution, LaTeX compilation, narrative agreement, task classification and scientific interpretation require independent review.'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    p.add_argument('--round',required=True)
    p.add_argument('--tasks',type=Path,default=TASKS)
    p.add_argument('--part',choices=['both','transport','inference'],default='both')
    p.add_argument('--output',type=Path,required=True)
    g=sub.add_parser('grade')
    g.add_argument('--round',required=True)
    g.add_argument('--tasks',type=Path,default=TASKS)
    g.add_argument('--answer',type=Path,required=True)
    g.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            text,manifest=prompt(args.round,args.tasks,args.part)
            args.output.mkdir(parents=True,exist_ok=False)
            (args.output/'prompt.txt').write_bytes(text.encode('utf-8'))
            (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            print(json.dumps(manifest))
            return 0
        if args.report.exists():
            raise ValueError('Use a new report path; refusing to overwrite an earlier trial')
        raw=args.answer.read_bytes()
        try:
            answer=parse_answer(raw.decode('utf-8'))
        except (ValueError,UnicodeError):
            report={'round':args.round,'parse_valid':False,'error':'Answer is not a valid JSON object',
                    'answer_sha256':hashlib.sha256(raw).hexdigest(),'numeric_checks_executed':False}
            args.report.parent.mkdir(parents=True,exist_ok=True)
            with args.report.open('x',encoding='utf-8') as stream:
                json.dump(report,stream,indent=2)
            print(json.dumps({'parse_valid':False,'numeric_checks_executed':False}))
            return 2
        report=grade(answer,args.round,args.tasks)
        report['parse_valid']=True
        report['answer_sha256']=hashlib.sha256(raw).hexdigest()
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2,ensure_ascii=False)
        print(json.dumps({'passed':report['passed'],'total':report['total']}))
        return 0 if report['passed']==report['total'] else 1
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'error':str(exc)}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
