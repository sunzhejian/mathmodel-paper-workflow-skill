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

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / 'examples/model-trials/tasks.json'
CONTEXT_FILES = ['SKILL.md', 'references/evidence-and-writing.md', 'references/mcm-icm.md']


def optimal_plans(data: dict, c: float) -> list[dict]:
    capacity = data['rocket_capacity_kg'] / 1000
    candidates = []
    for n in range(math.ceil(data['demand_tonnes'] / capacity) + 1):
        e = max(0, data['demand_tonnes'] - n * capacity)
        if e <= data['elevator_capacity_tonnes']:
            candidates.append({'e_tonnes': e, 'launches': n,
                               'cost': n * data['rocket_cost'] + e * c})
    best = min(p['cost'] for p in candidates)
    return [p for p in candidates if math.isclose(p['cost'], best, rel_tol=1e-10, abs_tol=1e-7)]


def switch_values(data: dict) -> list[float]:
    # Pairwise cost intersections are filtered by the lower envelope; crossings
    # of dominated plans are not decision switches.
    capacity = data['rocket_capacity_kg'] / 1000
    candidates = [(n, max(0, data['demand_tonnes'] - n * capacity))
                  for n in range(math.ceil(data['demand_tonnes'] / capacity) + 1)
                  if max(0, data['demand_tonnes'] - n * capacity) <= data['elevator_capacity_tonnes']]
    result = []
    for n, e in candidates:
        for m, f in candidates:
            if n >= m or e == f:
                continue
            c = (m - n) * data['rocket_cost'] / (e - f)
            if data['cost_range'][0] <= c <= data['cost_range'][1] and len(optimal_plans(data, c)) > 1:
                if not any(math.isclose(c, x, rel_tol=1e-9) for x in result):
                    result.append(c)
    return sorted(result)


def prompt(round_name: str) -> tuple[str, dict]:
    tasks = json.loads(TASKS.read_text(encoding='utf-8'))
    data = tasks['rounds'][round_name]
    contexts, hashes = [], {}
    for filename in CONTEXT_FILES:
        raw = (ROOT / filename).read_bytes()
        hashes[filename] = hashlib.sha256(raw).hexdigest()
        contexts.append(f'\n--- {filename} ---\n{raw.decode("utf-8")}')
    text = tasks['response_request'] + '\n' + ''.join(contexts)
    for kind in ('transport', 'inference'):
        text += f'\n\nTASK {kind}:\n{tasks[kind + "_request"]}\nINPUT DATA:\n{json.dumps(data[kind])}'
    manifest = {'round': round_name, 'task_sha256': hashlib.sha256(TASKS.read_bytes()).hexdigest(),
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


def plans_match(got: object, expected: list[dict]) -> bool:
    if not isinstance(got, list) or len(got) != len(expected):
        return False
    try:
        ordered = sorted(got, key=lambda x: x['launches'])
        expected = sorted(expected, key=lambda x: x['launches'])
        for a, b in zip(ordered, expected):
            for key in ('e_tonnes', 'launches', 'cost'):
                value = a[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                if not math.isfinite(value) or not math.isclose(value, b[key], rel_tol=1e-7, abs_tol=1e-6):
                    return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def word_count(text: object) -> int:
    # Declared English fixture convention: whitespace-delimited tokens containing
    # letters/digits. Punctuation-only tokens do not count; 28,600 counts once.
    return sum(bool(re.search(r'\w', token)) for token in text.split()) if isinstance(text,str) else 0


def rank_diagnostics(data: dict, interval: object) -> dict:
    alpha=data['judge_weight']
    judge=data['judge_share_a']
    expected=(1-alpha*(2*judge-1)/(1-alpha))/2
    def scores(p):
        return {'fan_share_a':p,'combined_a':alpha*judge+(1-alpha)*p,
                'combined_b':alpha*(1-judge)+(1-alpha)*(1-p)}
    result={'ranking_interpretation':'Combined score s_A > s_B, using the supplied weighting definition',
            'expected_lower':expected,'boundary_substitution':scores(expected)}
    got=interval.get('lower') if isinstance(interval,dict) else None
    if not isinstance(got,bool) and isinstance(got,(int,float)) and math.isfinite(got) and 0<=got<=1 and not math.isclose(got,expected,abs_tol=1e-8):
        p=(got+expected)/2
        witness=scores(p)
        witness['inside_proposed_interval']=p>got
        witness['original_ranking_holds']=witness['combined_a']>witness['combined_b']
        result['counterexample']=witness
    return result


def grade(answer: dict, round_name: str) -> dict:
    data = json.loads(TASKS.read_text(encoding='utf-8'))['rounds'][round_name]
    findings = []
    def check(name, passed, detail=''):
        findings.append({'check': name, 'passed': bool(passed), 'detail': detail})
    t = answer.get('transport', {})
    i = answer.get('inference', {})
    if not isinstance(t, dict): t = {}
    if not isinstance(i, dict): i = {}
    d = data['transport']
    check('nominal_optimum', plans_match(t.get('nominal_plans'), optimal_plans(d, d['nominal_cost_per_tonne'])))
    endpoints = t.get('endpoint_plans', [])
    for c in d['cost_range']:
        got = next((p.get('plans') for p in endpoints if isinstance(p, dict) and p.get('cost_per_tonne') == c), None) if isinstance(endpoints, list) else None
        check(f'endpoint_{c}', plans_match(got, optimal_plans(d, c)))
    expected = switch_values(d)
    got = t.get('switches', [])
    valid = isinstance(got, list) and len(got) == len(expected)
    if valid:
        try:
            got = sorted(got, key=lambda x:x['cost_per_tonne'])
            valid = all(math.isclose(p['cost_per_tonne'], c, rel_tol=1e-7) and plans_match(p['plans'], optimal_plans(d,c)) for p,c in zip(got,expected))
        except (KeyError, TypeError, ValueError): valid = False
    check('switches_and_all_ties', valid)
    for field, lo, hi in [('summary',70,110),('letter',130,190)]:
        count = word_count(t.get(field))
        check(field+'_length',lo <= count <= hi,f'{count} words; content needs separate review')
    for field in ['solver_source','latex_model','uncertainty_kind']:
        check('transport_'+field+'_present', isinstance(t.get(field),str) and bool(t[field].strip()))
    v = data['inference']
    p = (v['observed_combined_share_a'] - v['judge_weight'] * v['judge_share_a']) / (1-v['judge_weight'])
    lower = max(0, (1-v['judge_weight']*(2*v['judge_share_a']-1)/(1-v['judge_weight']))/2)
    point = i.get('point_share_a')
    check('exact_share',not isinstance(point,bool) and isinstance(point,(int,float)) and math.isfinite(point) and math.isclose(point,p,rel_tol=1e-7))
    interval = i.get('rank_interval_a', {})
    try:
        numeric=all(not isinstance(interval[k],bool) and isinstance(interval[k],(int,float)) and math.isfinite(interval[k]) for k in ['lower','upper'])
        correct = (numeric and math.isclose(interval['lower'],lower,rel_tol=1e-7) and interval['upper']==1
                   and interval['lower_inclusive'] is False and interval['upper_inclusive'] is True)
    except (KeyError,TypeError,ValueError): correct = False
    check('rank_identification_set',correct)
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
    p.add_argument('--round',choices=['baseline','holdout'],required=True)
    p.add_argument('--output',type=Path,required=True)
    g=sub.add_parser('grade')
    g.add_argument('--round',choices=['baseline','holdout'],required=True)
    g.add_argument('--answer',type=Path,required=True)
    g.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            text,manifest=prompt(args.round)
            args.output.mkdir(parents=True,exist_ok=False)
            (args.output/'prompt.txt').write_text(text,encoding='utf-8')
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
        report=grade(answer,args.round)
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
