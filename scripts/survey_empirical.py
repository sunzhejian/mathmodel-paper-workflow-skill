"""Reproducible exploratory survey tables from an explicit, question-bound plan.

Not a SEM engine. Two-group Firth estimates below apply ONLY to an intercept and
one binary predictor (a saturated two-group binomial logistic model).
"""
from pathlib import Path
from collections import Counter
from itertools import combinations
import argparse,csv,json,math,hashlib,importlib.metadata
import numpy as np
from scipy.stats import fisher_exact,rankdata
from scipy.stats.contingency import odds_ratio

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clean(v):
    if isinstance(v,dict):return {k:clean(x)for k,x in v.items()}
    if isinstance(v,(list,tuple,np.ndarray)):return[clean(x)for x in v]
    if isinstance(v,(float,np.floating)):return float(v)if math.isfinite(v)else('inf'if v>0 else'-inf'if v<0 else None)
    if isinstance(v,np.integer):return int(v)
    return v
def holm(values):
    order=sorted(range(len(values)),key=lambda i:(values[i],i));out=[None]*len(values);last=0
    for rank,i in enumerate(order):last=max(last,min(1,(len(values)-rank)*values[i]));out[i]=last
    return out
def adjust(rows,key='p',target='p_holm'):
    valid=[r for r in rows if r.get(key)is not None]
    for r,p in zip(valid,holm([r[key]for r in valid])):r[target]=p
    for r in rows:r['family_tests']=len(valid);r.setdefault(target,None)
def exact(a,b,c,d):
    # Rows: exposed/reference; columns: positive/negative.
    tab=np.array([[a,b],[c,d]],dtype=int);n=tab.sum()
    if min(a+b,c+d,a+c,b+d)==0:return {'p':None,'or_conditional':None,'or_low':None,'or_high':None,'status':'constant_or_empty_margin'}
    fit=odds_ratio(tab,kind='conditional');ci=fit.confidence_interval(confidence_level=.95)
    return {'p':float(fisher_exact(tab).pvalue),'or_conditional':float(fit.statistic),'or_low':float(ci.low),'or_high':float(ci.high),'status':'estimated'}
def tables(questionnaire,data,plan):
    allowed={'outcome','contrasts','ordinal','groups','rank_pairs','multiple','cooccurrence','conditional_number','price_group','seed','resamples','interpretation','title','version'}
    if set(plan)-allowed:raise ValueError('Unsupported analysis plan fields: '+','.join(sorted(set(plan)-allowed)))
    qs={q['id']:q for q in questionnaire['questions']};rows=data['records']
    if not rows or len({r['id']for r in rows})!=len(rows):raise ValueError('Empty cohort or repeated record IDs')
    sources={r.get('source')for r in rows}
    if len(sources)!=1 or not sources<={'ai_synthetic','human_reported'}:raise ValueError('Separate and explicitly label answer sources before analysis')
    if isinstance(data.get('source'),str)and data['source']in {'ai_synthetic','human_reported'}and data['source']not in sources:raise ValueError('Declared source conflicts with records')
    if data.get('questionnaire')is not None and data['questionnaire']!=questionnaire:raise ValueError('Questionnaire snapshot differs')
    outcome=plan['outcome'];oid=outcome['question'];pos=set(outcome['positive']);neg=set(outcome['negative'])
    def outcome_conditioned(q):
        seen=set()
        while q.get('showIf'):
            parent=q['showIf']['questionId']
            if parent==oid:return True
            if parent in seen:raise ValueError('Cyclic question branch')
            seen.add(parent);q=qs[parent]
        return False
    if pos&neg or not(pos|neg)<={o['id']for o in qs[oid]['options']}:raise ValueError('Outcome coding conflicts with questionnaire')
    for qid in plan.get('ordinal',{}):
        if len(set(plan['ordinal'][qid]))!=len(plan['ordinal'][qid])or not set(plan['ordinal'][qid])<={o['id']for o in qs[qid]['options']}:raise ValueError('Ordinal coding is not explicit and unique')
    applicable=lambda r,q: True if not q.get('showIf')else(r['answers'].get(q['showIf']['questionId'])==q['showIf']['value']if q['showIf']['operator']=='eq'else r['answers'].get(q['showIf']['questionId'])in q['showIf']['value']if q['showIf']['operator']=='in'else (_ for _ in()).throw(ValueError('Unsupported branch operator')))
    profile=[]
    for qid,q in qs.items():
        vals=[];structural=0;missing=0
        for r in rows:
            a=r['answers'].get(qid)
            if not applicable(r,q):
                if a not in [None,'',[]]:raise ValueError('Answer outside declared branch: '+qid)
                structural+=1;continue
            if a in [None,'',[]]:missing+=1;continue
            if q['type']in ['single','multiple']:
                if q['type']=='multiple'and not isinstance(a,list):raise ValueError('Multiple response must be an array: '+qid)
                if q['type']=='single'and not isinstance(a,str):raise ValueError('Single response must be an option code: '+qid)
                codes={o['id']for o in q['options']};chosen=a if isinstance(a,list)else[a]
                if not set(chosen)<=codes or len(chosen)!=len(set(chosen)):raise ValueError('Invalid option: '+qid)
                if q['type']=='multiple'and not(q.get('minSelections',0)<=len(chosen)<=q.get('maxSelections',len(codes))):raise ValueError('Invalid selection count')
            elif q['type']=='number':
                if isinstance(a,bool)or not isinstance(a,(float,int))or not math.isfinite(a)or not q.get('min',-math.inf)<=a<=q.get('max',math.inf):raise ValueError('Invalid number')
            vals.append(json.dumps(sorted(a)if q['type']=='multiple'else a,ensure_ascii=False,sort_keys=True))
        counts=Counter(vals);modal=max(counts.values(),default=0)
        profile.append({'question':qid,'type':q['type'],'applicable_n':len(rows)-structural,'valid_n':len(vals),'structural_skip':structural,'missing':missing,'distinct_answers':len(counts),'modal_n':modal,'modal_pct':100*modal/len(vals)if vals else None,'constant':len(counts)<=1})
    cohort=[r for r in rows if r['answers'].get(oid)in pos|neg];y=np.array([int(r['answers'][oid]in pos)for r in cohort]);n=len(y)
    if n<3 or y.sum()in[0,n]:raise ValueError('Binary outcome needs both observed outcomes')
    ordinal=[]
    for qid,codes in plan.get('ordinal',{}).items():
        vals=np.array([codes.index(r['answers'][qid])+1 for r in rows if r['answers'].get(qid)in codes],dtype=int)
        if not len(vals):ordinal.append({'question':qid,'valid_n':0,'status':'no_eligible_ordinal_values'});continue
        freq=np.bincount(vals,minlength=len(codes)+1)[1:];p=freq[freq>0]/len(vals)
        ordinal.append({'question':qid,'valid_n':len(vals),'code_min':int(vals.min()),'q25':float(np.quantile(vals,.25)),'median':float(np.median(vals)),'q75':float(np.quantile(vals,.75)),'code_max':int(vals.max()),'top_two_pct':100*sum(vals>=len(codes)-1)/len(vals),'modal_pct':100*freq.max()/len(vals),'normalized_entropy':float(-np.sum(p*np.log(p))/np.log(len(codes)))})
    contrasts=[];models=[];validation=[]
    baseline_probs=np.array([(int(y.sum())-int(yi)+.5)/n for yi in y])
    def scores(name,p):
        recall=float(np.mean(p[y==1]>=.5));specificity=float(np.mean(p[y==0]<.5))
        return {'model':name,'n':n,'events':int(y.sum()),'brier':float(np.mean((p-y)**2)),'log_loss':float(-np.mean(y*np.log(p)+(1-y)*np.log1p(-p))),'pred_min':float(min(p)),'pred_max':float(max(p)),'threshold_accuracy':float(np.mean((p>=.5)==y)),'positive_recall':recall,'specificity':specificity,'balanced_accuracy':(recall+specificity)/2,'validation':'leave_one_out_refit'}
    validation.append(scores('intercept',baseline_probs))
    for item in plan.get('contrasts',[]):
        q=qs[item['question']];qid=q['id']
        if q['type']!='single':raise ValueError('Binary contrast needs a single-response variable')
        if qid==oid or outcome_conditioned(q):raise ValueError('Outcome or outcome-conditioned question cannot predict its own gating outcome')
        exposed=set(item['exposed']);reference=set(item['reference'])
        if not exposed or not reference or exposed&reference or exposed|reference!={r['answers'].get(qid)for r in cohort}:raise ValueError('Contrast must explicitly partition this cohort into nonempty groups')
        x=np.array([int(r['answers'][qid]in exposed)for r in cohort]);a=int(sum((x==1)&(y==1)));b=int(sum((x==1)&(y==0)));c=int(sum((x==0)&(y==1)));d=int(sum((x==0)&(y==0)))
        result={'question':qid,'label':item['label'],'exposed_positive':a,'exposed_negative':b,'reference_positive':c,'reference_negative':d,'exposed_rate':a/(a+b),'reference_rate':c/(c+d),'risk_difference_pp':100*(a/(a+b)-c/(c+d)),**exact(a,b,c,d)};contrasts.append(result)
        firth_b0=math.log((c+.5)/(d+.5));firth_b1=math.log((a+.5)*(d+.5)/((b+.5)*(c+.5)))
        finite=min(a,b,c,d)>0;beta=math.log(a*d/(b*c))if finite else None;se=math.sqrt(1/a+1/b+1/c+1/d)if finite else None
        models.append({'question':qid,'events':int(y.sum()),'predictors':1,'mle_finite':finite,'mle_beta':beta,'mle_se':se,'mle_or':math.exp(beta)if finite else None,'mle_or_wald_low':math.exp(beta-1.95996398454*se)if finite else None,'mle_or_wald_high':math.exp(beta+1.95996398454*se)if finite else None,'firth_intercept':firth_b0,'firth_beta':firth_b1,'firth_or':math.exp(firth_b1),'firth_method':'analytic Jeffreys penalty; intercept + one binary predictor only'})
        probs=[]
        for i in range(n):
            train=np.arange(n)!=i;group=(x==x[i])&train;probs.append((int(y[group].sum())+.5)/(int(group.sum())+1))
        validation.append(scores(qid,np.array(probs)))
    adjust(contrasts)
    seed=int(plan.get('seed',20261030));B=int(plan.get('resamples',19999))
    if not 999<=B<=199999:raise ValueError('Resampling budget must be explicit and bounded')
    associations=[]
    for index,dim in enumerate(plan.get('groups',[])):
        definition=next(d for d in questionnaire['dimensions']if d['id']==dim);codes=[v['id']for v in definition['values']];counts=np.array([sum(r['traits'].get(dim)==code for r in cohort)for code in codes]);paid=np.array([sum(r['traits'].get(dim)==code and yy for r,yy in zip(cohort,y))for code in codes]);keep=counts>0;counts=counts[keep];paid=paid[keep]
        if len(counts)<2:raise ValueError('Group comparison needs two nonempty groups')
        expected=counts*y.sum()/n;expected_no=counts*(n-y.sum())/n;obs=float(np.sum((paid-expected)**2/expected+(counts-paid-expected_no)**2/expected_no))
        simulated=np.random.default_rng(seed+index).multivariate_hypergeometric(counts,int(y.sum()),size=B);stat=np.sum((simulated-expected)**2/expected+(counts-simulated-expected_no)**2/expected_no,axis=1);extreme=int(sum(stat>=obs-1e-12));p_mc=(extreme+1)/(B+1)
        p_exact=None;enumerated=0;events=min(int(y.sum()),int(n-y.sum()))
        if math.comb(events+len(counts)-1,len(counts)-1)<=100000:
            expected_small=counts*events/n;expected_large=counts*(n-events)/n;denominator=math.comb(n,events);tails=[]
            def enumerate_counts(prefix,left):
                nonlocal enumerated
                i=len(prefix)
                if i==len(counts)-1:
                    if left>counts[i]:return
                    v=np.array(prefix+[left]);enumerated+=1
                    statistic=float(np.sum((v-expected_small)**2/expected_small+(counts-v-expected_large)**2/expected_large))
                    if statistic>=obs-1e-12:tails.append(math.prod(math.comb(int(size),int(k))for size,k in zip(counts,v))/denominator)
                    return
                for k in range(min(left,int(counts[i]))+1):enumerate_counts(prefix+[k],left-k)
            enumerate_counts([],events);p_exact=min(1.0,math.fsum(tails))
        p=p_exact if p_exact is not None else p_mc
        r=len(counts);phi2=obs/n;den=min((r-1)-(r-1)**2/(n-1),1-1/(n-1));corrected=math.sqrt(max(0,phi2-(r-1)/(n-1))/den)
        associations.append({'dimension':dim,'groups':r,'n':n,'events':int(y.sum()),'chi2':obs,'cramers_v':math.sqrt(phi2),'v_bias_corrected':corrected,'min_expected':float(min(expected.min(),expected_no.min())),'expected_under_5':int(sum(expected<5)+sum(expected_no<5)),'p':p,'p_exact':p_exact,'enumerated_tables':enumerated,'p_mc':p_mc,'mc_se':math.sqrt(p_mc*(1-p_mc)/(B+1)),'resamples':B,'seed':seed+index,'extreme':extreme,'method':'fixed_margin_Pearson_exact'if p_exact is not None else'fixed_margin_Pearson_MC'})
    adjust(associations)
    rank_results=[]
    for index,(left,right)in enumerate(plan.get('rank_pairs',[])):
        lc=plan['ordinal'][left];rc=plan['ordinal'][right];pairs=[(lc.index(r['answers'][left])+1,rc.index(r['answers'][right])+1)for r in rows if r['answers'].get(left)in lc and r['answers'].get(right)in rc]
        if len(pairs)<3:rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':None,'p':None,'status':'insufficient_pairs'});continue
        a,b=np.array(pairs).T;a=rankdata(a);b=rankdata(b);a-=a.mean();b-=b.mean();den=np.linalg.norm(a)*np.linalg.norm(b)
        if den==0:rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':None,'p':None,'status':'constant'});continue
        rho=float(a@b/den);permuted=np.random.default_rng(seed+100+index).permuted(np.broadcast_to(b,(B,len(b))),axis=1);null=permuted@a/den;p=(int(sum(np.abs(null)>=abs(rho)-1e-12))+1)/(B+1)
        rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':rho,'p':p,'status':'estimated','resamples':B,'seed':seed+100+index})
    adjust(rank_results)
    multi=[];pairs=[]
    for qid in plan.get('multiple',[]):
        q=qs[qid]
        if q['type']!='multiple' or outcome_conditioned(q):raise ValueError('Do not compare outcome-conditioned multiple responses against their own outcome')
        accepted=[(r,int(yy))for r,yy in zip(cohort,y)if applicable(r,q)and isinstance(r['answers'].get(qid),list)];positive=sum(yy for r,yy in accepted);negative=len(accepted)-positive;family=[]
        for option in q['options']:
            code=option['id'];a=sum(yy==1 and code in r['answers'][qid]for r,yy in accepted);c=sum(yy==0 and code in r['answers'][qid]for r,yy in accepted);b=positive-a;d=negative-c
            family.append({'question':qid,'option':code,'label':option['label'],'paid_selected':a,'paid_n':positive,'free_selected':c,'free_n':negative,'paid_pct':100*a/positive,'free_pct':100*c/negative,'difference_pp':100*(a/positive-c/negative),**exact(a,b,c,d)})
        adjust(family);multi.extend(family)
        if qid not in plan.get('cooccurrence',[]):continue
        for one,two in combinations(q['options'],2):
            flags=[(one['id']in r['answers'][qid],two['id']in r['answers'][qid])for r,yy in accepted];a=sum(x and z for x,z in flags);b=sum(x and not z for x,z in flags);c=sum(not x and z for x,z in flags);d=len(flags)-a-b-c;den=(a+b)*(a+c)
            pairs.append({'question':qid,'one':one['id'],'two':two['id'],'one_label':one['label'],'two_label':two['label'],'n':len(flags),'both':a,'one_only':b,'two_only':c,'neither':d,'jaccard':a/(a+b+c)if a+b+c else None,'lift':a*len(flags)/den if den else None,'one_to_two':a/(a+b)if a+b else None,'two_to_one':a/(a+c)if a+c else None,'phi':(a*d-b*c)/math.sqrt((a+b)*(a+c)*(b+d)*(c+d))if min(a+b,a+c,b+d,c+d)>0 else None})
    price=[]
    number=plan.get('conditional_number')
    if number:
        for item in plan.get('contrasts',[])[:]:
            if item['question']!=plan.get('price_group'):continue
            for label,codes in [('exposed',item['exposed']),('reference',item['reference'])]:
                vals=[r['answers'][number]for r in cohort if r['answers'][oid]in pos and r['answers'][item['question']]in codes and r['answers'].get(number)is not None]
                price.append({'group':label,'n':len(vals),'min':min(vals)if vals else None,'q25':float(np.quantile(vals,.25))if vals else None,'median':float(np.median(vals))if vals else None,'q75':float(np.quantile(vals,.75))if vals else None,'max':max(vals)if vals else None,'mean':float(np.mean(vals))if vals else None})
    return clean({'cohort_summary':[{'records':len(rows),'binary_n':n,'positive':int(y.sum()),'negative':int(n-y.sum()),'excluded_outcome':len(rows)-n,'source':rows[0].get('source')}],'measurement_profile':profile,'ordinal_summary':ordinal,'binary_contrasts':contrasts,'group_permutation':associations,'rank_permutation':rank_results,'multiple_contrasts':multi,'cooccurrence':pairs,'logistic_models':models,'loo_validation':validation,'conditional_price':price})

def run(questionnaire,data,plan,out,overwrite=False):
    out=Path(out);inputs={str(label):sha(file)for label,file in [('questionnaire',questionnaire),('data',data),('plan',plan)]}
    previous=None
    if out.exists()and any(out.iterdir()):
        if not overwrite:raise ValueError('Choose a new output directory or explicitly permit verified generated-file replacement')
        previous=json.loads((out/'manifest.json').read_text(encoding='utf8'))
        if previous['input_sha256']!=inputs:raise ValueError('Inputs changed; preserve this version and use a new directory')
        for f in previous['files']:
            if sha(out/f['path'])!=f['sha256']:raise ValueError('Generated file was edited; preserve it and use a new directory')
    content=tables(json.loads(Path(questionnaire).read_text(encoding='utf8')),json.loads(Path(data).read_text(encoding='utf8')),json.loads(Path(plan).read_text(encoding='utf8')))
    out.mkdir(parents=True,exist_ok=True);files=[]
    def register(p):files.append({'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size})
    for name,rows in content.items():
        if not rows:continue
        p=out/(name+'.csv');keys=list(dict.fromkeys(k for row in rows for k in row))
        with p.open('w',encoding='utf-8-sig',newline='')as f:
            safe=lambda v:"'"+v if isinstance(v,str)and v.lstrip().startswith(('=','+','-','@','\t','\r'))else v
            w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:safe(v)for k,v in row.items()}for row in rows)
        register(p)
    p=out/'results.json';p.write_text(json.dumps({'input_sha256':inputs,'analysis':content,'source':json.loads(Path(data).read_text(encoding='utf8')).get('source'),'inference_scope':'Exploratory record-structure diagnostics under stated reference models; no causal or population claim','software':{k:importlib.metadata.version(k)for k in ['numpy','scipy']}},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');register(p)
    (out/'manifest.json').write_text(json.dumps({'input_sha256':inputs,'program_sha256':sha(__file__),'files':files},ensure_ascii=False,indent=2),encoding='utf8')
    return {'tables':len(files)-1,'rows':{k:len(v)for k,v in content.items()},'output':str(out)}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--questionnaire',required=True);p.add_argument('--data',required=True);p.add_argument('--plan',required=True);p.add_argument('--out',required=True);p.add_argument('--overwrite-generated',action='store_true');a=p.parse_args();print(json.dumps(run(a.questionnaire,a.data,a.plan,a.out,a.overwrite_generated),ensure_ascii=False))
