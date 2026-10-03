"""Independent, deterministic oracle for the synthetic full-paper fixture."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import numpy as np

NAMES=('mean','seasonal_naive','linear_trend','trend_weekly')
def features(t,weekly=False):
    cols=[np.ones(len(t)),t]
    if weekly:cols += [np.sin(2*np.pi*t/7),np.cos(2*np.pi*t/7)]
    return np.column_stack(cols)
def forecast(name,t,y,future):
    if name=='mean':return np.full(len(future),np.mean(y)),[float(np.mean(y))]
    if name=='seasonal_naive':
        return np.array([y[-7+int((d-t[-1]-1)%7)] for d in future]),y[-7:].tolist()
    weekly=name=='trend_weekly';coef=np.linalg.lstsq(features(t,weekly),y,rcond=None)[0]
    return features(future,weekly)@coef,coef.tolist()
def metrics(p,y):
    error=p-y
    return {'rmse':float(np.sqrt(np.mean(error**2))),'mae':float(np.mean(abs(error))),'bias':float(np.mean(error))}
def fleet(q,cp=.2):
    if not np.isfinite(q) or q<0:raise ValueError('Finite nonnegative order required')
    candidates=[]
    for a in range(7):
        for b in range(5):
            cap=22*a+35*b
            if cap+1e-9>=q:
                emission=45*a+65*b;cost=1100*a+1800*b+cp*emission
                candidates.append((cost,cap-q,a,b))
    if not candidates:raise ValueError('Order exceeds fleet capacity')
    best=min(c[0] for c in candidates)
    ties=[c for c in candidates if abs(c[0]-best)<1e-8]
    chosen=min(ties,key=lambda v:(v[1],v[2],v[3]))
    return chosen[2],chosen[3],[(v[2],v[3]) for v in ties]
def simulate(days,y,p,s,cp=.2,shortage_price=600,scale=1):
    inventory=float(s);rows=[]
    for day,actual,predicted in zip(days,y*scale,p):
        order=max(0,float(predicted)+s-inventory)
        a,b,_=fleet(order,cp)
        served=min(float(actual),inventory+order)
        shortage=float(actual)-served;inventory=inventory+order-served
        emission=45*a+65*b
        rows.append({'day':int(day),'actual':float(actual),'predicted':float(predicted),
                     'order':order,'served':served,'shortage':shortage,'inventory':inventory,
                     'a':a,'b':b,'fleet_cost':1100*a+1800*b,'carbon_cost':cp*emission,
                     'holding_cost':10*inventory,'shortage_cost':shortage_price*shortage,'emissions':emission})
    sums={k:sum(r[k] for r in rows) for k in ['fleet_cost','carbon_cost','holding_cost','shortage_cost','emissions','shortage']}
    result={k:sums[k] for k in ['fleet_cost','carbon_cost','holding_cost','shortage_cost','emissions']}
    result.update(total_cost=sum(sums[k] for k in ['fleet_cost','carbon_cost','holding_cost','shortage_cost']),
                  fill_rate=sum(r['served'] for r in rows)/sum(r['actual'] for r in rows),
                  shortage_tonnes=sums['shortage'],mean_stock=sum(r['inventory'] for r in rows)/len(rows))
    return result,rows
def select(days,y,p,stocks,scales,cp=.2,sp=600):
    grid={s:simulate(days,y,p,s,cp,sp)[0] for s in stocks}
    nominal=min(stocks,key=lambda s:(grid[s]['total_cost'],s))
    matrix=np.array([[simulate(days,y,p,s,cp,sp,k)[0]['total_cost'] for s in stocks] for k in scales])
    regret=matrix-matrix.min(axis=1,keepdims=True)
    robust=min(stocks,key=lambda s:(regret[:,stocks.index(s)].max(),s))
    return nominal,robust,grid,regret
def solve(folder):
    cfg=json.loads((folder/'case.json').read_text(encoding='utf-8'))
    # The oracle is a fixed benchmark, not a generic logistics simulator. Reject
    # unsupported contracts instead of judging a model against silently ignored
    # changed parameters.
    required={'schema_version':1,'training_end':120,'validation_end':150,'test_end':180,'forecast_end':210,
              'safety_stocks':[0,5,10,15,20,25,30],'demand_scales':[.85,.925,1,1.075,1.15],
              'fleet':{'A':{'capacity':22,'cost':1100,'emission':45,'max':6},'B':{'capacity':35,'cost':1800,'emission':65,'max':4}},
              'carbon_prices':[0,.2,.5],'shortage_costs':[300,600,900],'holding_cost':10,'base_carbon_price':.2,'base_shortage_cost':600}
    if any(cfg.get(k)!=v for k,v in required.items()):raise ValueError('Unsupported case parameters: this oracle checks the frozen forecast-inventory-fleet-v1 contract only')
    with (folder/'demand.csv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
    days=np.array([float(r['day']) for r in rows]); y=np.array([float(r['demand_tonnes']) for r in rows])
    if len(rows)!=180 or not np.array_equal(days,np.arange(1,181)) or not np.isfinite(y).all() or (y<0).any():
        raise ValueError('Fixture requires 180 finite chronological nonnegative demands')
    val={};preds={}
    for name in NAMES:
        p,_=forecast(name,days[:120],y[:120],days[120:150]);val[name]=metrics(p,y[120:150]);preds[name]=p
    name=min(NAMES,key=lambda k:(val[k]['rmse'],NAMES.index(k)))
    future,coef=forecast(name,days[:150],y[:150],np.arange(151,211))
    test_p=future[:30];stocks=cfg['safety_stocks'];scales=cfg['demand_scales']
    nominal,robust,_,_=select(days[120:150],y[120:150],preds[name],stocks,scales)
    baselines={label:simulate(days[150:],y[150:],test_p,s)[0] for label,s in [('nominal',nominal),('robust',robust)]}
    scenarios=[]
    for scale in scales:
        values={s:simulate(days[150:],y[150:],test_p,s,scale=scale)[0] for s in stocks}
        optimum=min(v['total_cost'] for v in values.values())
        for s,v in values.items():scenarios.append({'scale':scale,'stock':s,**v,'regret':v['total_cost']-optimum})
    sensitivities=[]
    for cp in cfg['carbon_prices']:
        for sp in cfg['shortage_costs']:
            ns,rs,_,_=select(days[120:150],y[120:150],preds[name],stocks,scales,cp,sp)
            sensitivities.append({'carbon_price':cp,'shortage_price':sp,'nominal_stock':ns,'robust_stock':rs,
                                  'test_nominal_cost':simulate(days[150:],y[150:],test_p,ns,cp,sp)[0]['total_cost'],
                                  'test_robust_cost':simulate(days[150:],y[150:],test_p,rs,cp,sp)[0]['total_cost']})
    return {'forecasts':{'selected_model':name,'validation_metrics':val,'test_metrics':metrics(test_p,y[150:]),'coefficients':coef},
            'policies':{'nominal_stock':nominal,'robust_stock':robust},'baseline':baselines,
            'scenarios':scenarios,'sensitivity':sensitivities}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=solve(args.data_dir);args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'selected_model':result['forecasts']['selected_model'],'policies':result['policies']},ensure_ascii=False))
if __name__=='__main__':main()
