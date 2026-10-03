"""Run reviewed model source and compare the full synthetic case independently.

This is an evidence checker, not an OS sandbox or scientific quality score.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
try:
    import complete_case_reference as ref
except ImportError:
    from scripts import complete_case_reference as ref
import numpy as np

ALIASES={'mean':'mean','training_mean':'mean','seasonal_naive':'seasonal_naive','linear':'linear_trend',
         'linear_trend':'linear_trend','periodic':'trend_weekly','trend_seasonal':'trend_weekly','trend_weekly':'trend_weekly'}
def close(a,b):
    return isinstance(a,(int,float)) and not isinstance(a,bool) and math.isfinite(a) and math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-7)
def read_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return [{k:float(v) for k,v in r.items()} for r in csv.DictReader(f)]
def compare(input_dir,result_dir):
    expected=ref.solve(input_dir);actual=json.loads((result_dir/'results.json').read_text(encoding='utf-8'));errors=[];checks=0
    def check(ok,message):
        nonlocal checks
        checks+=1
        if not ok:errors.append(message)
    def numeric(a,b,path):
        if isinstance(b,dict):
            for k,v in b.items():
                if not isinstance(a,dict) or k not in a:check(False,path+'.'+k+': missing')
                else:numeric(a[k],v,path+'.'+k)
        else:check(close(a,b),path+': differs from independent calculation')
    af=actual.get('forecasts',{});ef=expected['forecasts']
    check(ALIASES.get(af.get('selected_model'))==ef['selected_model'],'forecast model choice')
    vm={ALIASES.get(k,k):v for k,v in af.get('validation_metrics',{}).items()}
    numeric(vm,ef['validation_metrics'],'validation metrics');numeric(af.get('test_metrics',{}),ef['test_metrics'],'test metrics')
    coeff=af.get('coefficients',[])
    check(len(coeff)==len(ef['coefficients']) and all(close(a,b) for a,b in zip(coeff,ef['coefficients'])),'refitted coefficients')
    numeric(actual.get('policies',{}),expected['policies'],'policies')
    numeric(actual.get('baseline',{}),expected['baseline'],'test baseline')
    sens={(r['carbon_price'],r['shortage_price']):r for r in actual.get('sensitivity',[])}
    check(len(sens)==9,'nine sensitivity combinations')
    for r in expected['sensitivity']:numeric(sens.get((r['carbon_price'],r['shortage_price']),{}),r,'sensitivity '+str((r['carbon_price'],r['shortage_price'])))
    raw=read_csv(input_dir/'demand.csv');days=np.array([r['day'] for r in raw]);y=np.array([r['demand_tonnes'] for r in raw])
    name=ef['selected_model'];vp,_=ref.forecast(name,days[:120],y[:120],days[120:150]);tp,_=ref.forecast(name,days[:150],y[:150],days[150:])
    for stem,d,obs,pred in [('daily-validation',days[120:150],y[120:150],vp),('daily-test',days[150:],y[150:],tp)]:
        _,rows=ref.simulate(d,obs,pred,expected['policies']['nominal_stock'])
        got=read_csv(result_dir/(stem+'.csv'));check(len(got)==30,stem+' row count')
        for i,(a,b) in enumerate(zip(got,rows)):numeric(a,b,stem+' row '+str(i))
    forecast_rows=read_csv(result_dir/'forecast.csv')
    forecasts={r['day']:r['predicted'] for r in forecast_rows}
    check(len(forecasts)==len(forecast_rows),'forecast date IDs are unique')
    future,_=ref.forecast(name,days[:150],y[:150],np.arange(151,211))
    for t,p in zip(range(151,211),future):check(close(forecasts.get(t),p),'forecast day '+str(t))
    policies=read_csv(result_dir/'policy-grid.csv');pg={r['stock']:r for r in policies}
    check(len(pg)==len(policies)==7,'complete test policy grid')
    for s in [0,5,10,15,20,25,30]:
        expected_policy=ref.simulate(days[150:],y[150:],tp,s)[0]
        numeric(pg.get(s,{}),{'stock':s,**{k:expected_policy[k] for k in ['total_cost','fill_rate','emissions']}},'test policy grid '+str(s))
    scenarios=read_csv(result_dir/'scenario-grid.csv');grid={(r['scale'],r['stock']):r for r in scenarios}
    check(len(scenarios)==len(grid)==35,'complete test scenario grid (5 x 7)')
    for r in expected['scenarios']:numeric(grid.get((r['scale'],r['stock']),{}),{k:r[k] for k in ['scale','stock','total_cost','fill_rate','emissions','regret']},'scenario '+str((r['scale'],r['stock'])))
    # JSON may expose only the frozen robust policy, but each exposed result must agree.
    reference={(r['scale'],r['stock']):r for r in expected['scenarios']}
    for r in actual.get('scenarios',[]):
        k=(r.get('scale'),r.get('stock'));check(k in reference,'JSON scenario key')
        if k in reference:numeric(r,{x:reference[k][x] for x in ['scale','stock','total_cost','fill_rate','emissions','regret']},'JSON scenario '+str(k))
    return {'passed':not errors,'checks':checks,'errors':errors,'scope':'specified synthetic inputs, forecasts, all daily rows and cost/scenario/sensitivity outputs; no general scientific guarantee'}
def run(source,input_dir,output):
    ref.solve(input_dir)  # Refuse unsupported benchmark parameters before code execution.
    tree=ast.parse(source.read_text(encoding='utf-8-sig'))
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            names=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module or '']
            if any(x.split('.')[0] not in {'argparse','csv','json','math','pathlib','numpy','typing'} for x in names):raise ValueError('Unreviewed import outside fixture allowlist')
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {'eval','exec','compile','__import__','input'}:raise ValueError('Dynamic execution is outside this fixture')
    output.mkdir(parents=True,exist_ok=False)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in input_dir.iterdir() if p.is_file()}
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PATH','USERPROFILE'}}
    env['PYTHONUTF8']='1'
    proc=subprocess.run([sys.executable,'-B','-X','utf8',str(source.resolve()),'--data-dir',str(input_dir.resolve()),'--output',str(output.resolve())],cwd=output,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'exit_code':proc.returncode,
            'input_preserved':before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in input_dir.iterdir() if p.is_file()},
            'stdout_tail':proc.stdout[-1200:],'stderr_tail':proc.stderr[-1200:]}
    if proc.returncode==0:
        try:report['numeric']=compare(input_dir,output)
        except Exception as exc:report['numeric']={'passed':False,'error_type':type(exc).__name__,'error':str(exc)[:500]}
    report['passed']=proc.returncode==0 and report['input_preserved'] and report.get('numeric',{}).get('passed',False)
    (output/'execution-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reviewed-source',action='store_true')
    args=p.parse_args()
    if not args.reviewed_source:p.error('Read the source before using --reviewed-source; this flag is not a sandbox')
    report=run(args.source,args.data_dir,args.output);print(json.dumps({'passed':report['passed'],'exit_code':report['exit_code'],'numeric_errors':len(report.get('numeric',{}).get('errors',[]))},ensure_ascii=False));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
