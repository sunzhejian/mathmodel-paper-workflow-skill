"""Execute a manually reviewed synthetic transport solver with frozen inputs.

Not an OS security sandbox: never run unreviewed generated programs. Provider
credential variables are excluded from the child environment.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
try:
    from model_trial import parse_answer,optimal_plans,plans_match,exact_switch_values
except ImportError:
    from scripts.model_trial import parse_answer,optimal_plans,plans_match,exact_switch_values


def execute(answer: Path,tasks: Path,output: Path,probes: Path | None = None) -> dict:
    raw=answer.read_bytes()
    value=parse_answer(raw.decode('utf-8'))
    source=value['transport']['solver_source']
    if not isinstance(source,str) or not source.strip():raise ValueError('Missing solver source')
    output.mkdir(parents=True,exist_ok=False)
    (output/'solver.py').write_bytes(source.encode('utf-8'))
    report={'answer_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'execution_performed':False}
    try:ast.parse(source)
    except SyntaxError as exc:
        report['syntax_error']={'message':exc.msg,'line':exc.lineno,'column':exc.offset}
        (output/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report
    data=json.loads(tasks.read_text(encoding='utf-8'))
    cases=[]
    expected=[]
    for name,row in data['rounds'].items():
        d=row['transport']
        costs=[(str(d['nominal_cost_per_tonne']),'nominal')]+[(str(c),'endpoint') for c in d['cost_range']]
        # Exact switch representation, not its rounded JSON display value.
        from fractions import Fraction
        for c in exact_switch_values(d):
            costs.append((str(c),'exact_switch'))
        for c,kind in costs:
            cases.append({'round':name,'kind':kind,'cost_expression':c,'arguments':[d[k] for k in ['demand_tonnes','elevator_capacity_tonnes','rocket_capacity_kg','rocket_cost']]})
            expected.append(optimal_plans(d,float(Fraction(c))))
    if probes:
        for d in json.loads(probes.read_text(encoding='utf-8'))['cases']:
            cases.append({'round':'solver_probe','kind':'fractional_geometry','id':d['id'],'cost_expression':str(d['cost_per_tonne']),
                          'arguments':[d[k] for k in ['demand_tonnes','elevator_capacity_tonnes','rocket_capacity_kg','rocket_cost']]})
            expected.append(optimal_plans(d,d['cost_per_tonne']))
    (output/'cases.json').write_text(json.dumps(cases),encoding='utf-8')
    driver='''import json,runpy
from fractions import Fraction
from pathlib import Path
base=Path(__file__).parent
solve=runpy.run_path(str(base/"solver.py"))["solve_transport"]
cases=json.loads((base/"cases.json").read_text(encoding="utf-8"))
result=[]
for case in cases:
    args=case["arguments"]
    if case["kind"]=="fractional_geometry":args=[Fraction(str(args[0])),Fraction(str(args[1])),args[2],args[3]]
    result.append(solve(*args,Fraction(case["cost_expression"])))
def exact_json(x):
    if isinstance(x,Fraction):return str(x.numerator)+"/"+str(x.denominator)
    raise TypeError("Unsupported solver return type")
print(json.dumps(result,default=exact_json))
'''
    (output/'driver.py').write_text(driver,encoding='utf-8')
    env={k:v for k,v in os.environ.items() if k.upper() in ['PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA']}
    proc=subprocess.Popen([sys.executable,'-I',str((output/'driver.py').resolve())],cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
    timed_out=False
    try:stdout,stderr=proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        timed_out=True
        proc.kill()
        stdout,stderr=proc.communicate()
    report.update({'execution_performed':True,'exit_code':proc.returncode,'timed_out':timed_out,'stderr_tail':stderr[-1200:]})
    if proc.returncode==0 and not timed_out:
        actual=json.loads(stdout)
        if not isinstance(actual,list) or len(actual)!=len(cases):raise ValueError('Solver returned an unexpected result set')
        rows=[{**case,'plans':plans,'matches_reference':plans_match(plans,ref,allow_fraction=data.get('schema_version',1)>=2)} for case,plans,ref in zip(cases,actual,expected)]
        report['cases']=rows
        report['passed']=sum(r['matches_reference'] for r in rows)
        report['total']=len(rows)
    report['all_checked_cases_pass']=len(cases)>0 and report.get('passed')==len(cases) and not timed_out
    report['limits']='Only frozen positive-cost inputs and exact switches; not a general solver proof or security sandbox.'
    (output/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--answer',type=Path,required=True)
    p.add_argument('--tasks',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--probes',type=Path)
    p.add_argument('--reviewed-source',action='store_true')
    a=p.parse_args()
    try:
        if not a.reviewed_source:raise ValueError('Source review required; no execution performed')
        r=execute(a.answer,a.tasks,a.output,a.probes)
        print(json.dumps({k:v for k,v in r.items() if k!='cases'}))
        return 0 if r.get('all_checked_cases_pass') else 1
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc),'all_checked_cases_pass':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
