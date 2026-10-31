"""Reproducible exploratory survey tables from an explicit, question-bound plan.

Not a SEM engine. Two-group Firth estimates below apply ONLY to an intercept and
one binary predictor (a saturated two-group binomial logistic model).
"""
from pathlib import Path
from collections import Counter
from itertools import combinations
import argparse,csv,json,math,hashlib,importlib.metadata,re
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

def question_index(questionnaire,rows):
    """Check the analysis boundary and share the editor's condition semantics."""
    qs={};dimensions={}
    for q in questionnaire['questions']:
        if not isinstance(q.get('id'),str)or not q['id']or q['id']in qs:raise ValueError('Duplicate or invalid question ID')
        if q.get('type')not in ['single','multiple','number','text']:raise ValueError('Unsupported question type')
        if q['type']in ['single','multiple']:
            codes=[o['id']for o in q['options']]
            if not codes or any(not isinstance(c,str)or not c for c in codes)or len(set(codes))!=len(codes):raise ValueError('Duplicate or invalid option ID')
        qs[q['id']]=q
    for dim in questionnaire.get('dimensions',[]):
        codes=[v['id']for v in dim['values']]
        if dim['id']in dimensions or not codes or len(codes)!=len(set(codes)):raise ValueError('Duplicate or empty dimension')
        dimensions[dim['id']]=set(codes)
    def refs(condition,depth=0):
        if not isinstance(condition,dict)or depth>8:raise ValueError('Invalid question branch depth or shape')
        composite=[k for k in ['all','any','not']if k in condition]
        if composite:
            key=composite[0]
            if len(condition)!=1 or len(composite)!=1:raise ValueError('Invalid composite question branch')
            parts=[condition[key]]if key=='not'else condition[key]
            if not isinstance(parts,list)or not 1<=len(parts)<=30:raise ValueError('Invalid composite question branch children')
            return set().union(*(refs(c,depth+1)for c in parts))
        parent=condition.get('questionId');op=condition.get('operator')
        if parent not in qs or op not in ['eq','neq','in','notIn','contains','answered']:raise ValueError('Unsupported branch reference or operator')
        if op!='answered'and 'value'not in condition:raise ValueError('Missing branch comparison value')
        if op in ['in','notIn']and(not isinstance(condition['value'],list)or not condition['value']):raise ValueError('Branch membership needs a nonempty list')
        if op=='contains'and qs[parent]['type']!='multiple':raise ValueError('Branch contains needs a multiple response')
        if qs[parent]['type']=='multiple'and op not in ['contains','answered']:raise ValueError('Invalid multiple response branch operator')
        return {parent}
    dependencies={qid:refs(q['showIf'])if q.get('showIf')is not None else set()for qid,q in qs.items()}
    done=set()
    def visit(qid,stack):
        if qid in stack:raise ValueError('Cyclic question branch')
        if qid not in done:
            for parent in dependencies[qid]:visit(parent,stack|{qid})
            done.add(qid)
    for qid in qs:visit(qid,set())
    for r in rows:
        if not isinstance(r.get('answers'),dict)or not isinstance(r.get('traits',{}),dict):raise ValueError('Answers and traits must be objects')
        if set(r['answers'])-set(qs):raise ValueError('Answer references an unknown question')
        for dim,codes in dimensions.items():
            value=r.get('traits',{}).get(dim)
            if value is not None and value!=''and value not in codes:raise ValueError('Unknown trait code for dimension '+dim)
    def answered(value):return value is not None and value!=''and value!=[]
    def applicable(row,q):
        condition=q.get('showIf')
        if condition is None:return True
        def value_at(qid):return row['answers'].get(qid)if applicable(row,qs[qid])else None
        def evaluate(c):
            if 'all'in c:return all(evaluate(v)for v in c['all'])
            if 'any'in c:return any(evaluate(v)for v in c['any'])
            if 'not'in c:return all(answered(value_at(qid))for qid in refs(c['not']))and not evaluate(c['not'])
            value=value_at(c['questionId']);op=c['operator']
            if op=='answered':return answered(value)
            if not answered(value):return False
            expected=c['value']
            if op=='eq':return value==expected
            if op=='neq':return value!=expected
            if op=='in':return value in expected
            if op=='notIn':return value not in expected
            return isinstance(value,list)and expected in value
        return evaluate(condition)
    def conditioned(qid,outcome,seen=None):
        seen=set()if seen is None else seen
        return any(parent==outcome or(parent not in seen and conditioned(parent,outcome,seen|{parent}))for parent in dependencies[qid])
    return qs,dimensions,applicable,conditioned

def missing_answer(q,value):
    return value is None or value==''or(value==[]and(q['type']!='multiple'or q.get('minSelections',0)>0))
def tables(questionnaire,data,plan):
    allowed={'outcome','contrasts','ordinal','groups','rank_pairs','multiple','cooccurrence','conditional_number','price_group','seed','resamples','interpretation','title','version'}
    if set(plan)-allowed:raise ValueError('Unsupported analysis plan fields: '+','.join(sorted(set(plan)-allowed)))
    rows=data['records']
    if not rows or any(not isinstance(r.get('id'),str)or not r['id'].strip()for r in rows)or len({r['id']for r in rows})!=len(rows):raise ValueError('Empty cohort or repeated/invalid record IDs')
    qs,dimensions,applicable,conditioned=question_index(questionnaire,rows)
    sources={r.get('source')for r in rows}
    if len(sources)!=1 or not sources<={'ai_synthetic','human_reported'}:raise ValueError('Separate and explicitly label answer sources before analysis')
    if isinstance(data.get('source'),str)and data['source']in {'ai_synthetic','human_reported'}and data['source']not in sources:raise ValueError('Declared source conflicts with records')
    if data.get('questionnaire')is not None and data['questionnaire']!=questionnaire:raise ValueError('Questionnaire snapshot differs')
    outcome=plan['outcome'];oid=outcome['question'];pos=set(outcome['positive']);neg=set(outcome['negative'])
    def outcome_conditioned(q):return conditioned(q['id'],oid)
    if oid not in qs or qs[oid]['type']!='single'or not pos or not neg or pos&neg or not(pos|neg)<={o['id']for o in qs[oid]['options']}:raise ValueError('Outcome coding conflicts with questionnaire')
    for key,default in [('seed',20261030),('resamples',19999)]:
        value=plan.get(key,default)
        if isinstance(value,bool)or not isinstance(value,int):raise ValueError(key+' must be an integer')
    if plan.get('seed',20261030)<0 or not 999<=plan.get('resamples',19999)<=199999:raise ValueError('Resampling seed or budget is out of range')
    if len(plan.get('groups',[]))!=len(set(plan.get('groups',[])))or not set(plan.get('groups',[]))<=set(dimensions):raise ValueError('Unknown or duplicate grouping dimension')
    for qid in plan.get('ordinal',{}):
        if qid not in qs or qs[qid]['type']!='single'or len(plan['ordinal'][qid])<2 or len(set(plan['ordinal'][qid]))!=len(plan['ordinal'][qid])or not set(plan['ordinal'][qid])<={o['id']for o in qs[qid]['options']}:raise ValueError('Ordinal coding needs at least two explicit unique options')
    for pair in plan.get('rank_pairs',[]):
        if len(pair)!=2 or any(qid not in plan.get('ordinal',{})for qid in pair):raise ValueError('Rank pairs must reference two ordinal plan variables')
    if not set(plan.get('cooccurrence',[]))<=set(plan.get('multiple',[])):raise ValueError('Cooccurrence must reference selected multiple response questions')
    profile=[]
    for qid,q in qs.items():
        vals=[];structural=0;missing=0
        for r in rows:
            a=r['answers'].get(qid)
            if not applicable(r,q):
                if a not in [None,'',[]]:raise ValueError('Answer outside declared branch: '+qid)
                structural+=1;continue
            if missing_answer(q,a):missing+=1;continue
            if q['type']in ['single','multiple']:
                if q['type']=='multiple'and not isinstance(a,list):raise ValueError('Multiple response must be an array: '+qid)
                if q['type']=='single'and not isinstance(a,str):raise ValueError('Single response must be an option code: '+qid)
                codes={o['id']for o in q['options']};chosen=a if isinstance(a,list)else[a]
                if not set(chosen)<=codes or len(chosen)!=len(set(chosen)):raise ValueError('Invalid option: '+qid)
                if q['type']=='multiple'and not(q.get('minSelections',0)<=len(chosen)<=q.get('maxSelections',len(codes))):raise ValueError('Invalid selection count')
            elif q['type']=='number':
                if isinstance(a,bool)or not isinstance(a,(float,int))or not math.isfinite(a)or not q.get('min',-math.inf)<=a<=q.get('max',math.inf):raise ValueError('Invalid number')
            elif not isinstance(a,str):raise ValueError('Text response must be a string')
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
    associations=[];group_cells=[]
    for index,dim in enumerate(plan.get('groups',[])):
        definition=next(d for d in questionnaire['dimensions']if d['id']==dim);codes=[v['id']for v in definition['values']]
        complete=[(r,int(yy))for r,yy in zip(cohort,y)if r.get('traits',{}).get(dim)in codes];gn=len(complete);success=sum(yy for r,yy in complete)
        counts=np.array([sum(r.get('traits',{}).get(dim)==code for r,yy in complete)for code in codes]);paid=np.array([sum(r.get('traits',{}).get(dim)==code and yy for r,yy in complete)for code in codes])
        for value,count,event in zip(definition['values'],counts,paid):group_cells.append({'dimension':dim,'level':value['id'],'label':value.get('label',value['id']),'n':int(count),'positive':int(event),'negative':int(count-event),'positive_pct':100*event/count if count else None,'eligible_n':gn})
        keep=counts>0;counts=counts[keep];paid=paid[keep]
        support={'dimension':dim,'groups':len(counts),'n':gn,'events':success,'binary_cohort_n':n,'excluded_group_missing':n-gn}
        if len(counts)<2 or success in [0,gn]:
            associations.append({**support,'p':None,'status':'constant_outcome'if gn and success in [0,gn]else'insufficient_groups','method':'not_estimated'});continue
        expected=counts*success/gn;expected_no=counts*(gn-success)/gn;obs=float(np.sum((paid-expected)**2/expected+(counts-paid-expected_no)**2/expected_no))
        rng=np.random.default_rng(seed+index);extreme=0;batch=B if B*len(counts)<=2000000 else max(1,2000000//len(counts))
        for start in range(0,B,batch):
            simulated=rng.multivariate_hypergeometric(counts,success,size=min(batch,B-start));stat=np.sum((simulated-expected)**2/expected+(counts-simulated-expected_no)**2/expected_no,axis=1);extreme+=int(sum(stat>=obs-1e-12))
        p_mc=(extreme+1)/(B+1);p_exact=None;enumerated=0;events=min(success,gn-success)
        if math.comb(events+len(counts)-1,len(counts)-1)<=100000:
            expected_small=counts*events/gn;expected_large=counts*(gn-events)/gn;denominator=math.comb(gn,events);tails=[]
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
        r=len(counts);phi2=obs/gn;den=min((r-1)-(r-1)**2/(gn-1),1-1/(gn-1));corrected=math.sqrt(max(0,phi2-(r-1)/(gn-1))/den)if den>0 else None
        associations.append({**support,'chi2':obs,'cramers_v':math.sqrt(phi2),'v_bias_corrected':corrected,'min_expected':float(min(expected.min(),expected_no.min())),'expected_under_5':int(sum(expected<5)+sum(expected_no<5)),'p':p,'p_exact':p_exact,'enumerated_tables':enumerated,'p_mc':p_mc,'mc_se':math.sqrt(p_mc*(1-p_mc)/(B+1)),'resamples':B,'seed':seed+index,'extreme':extreme,'status':'estimated','method':'fixed_margin_Pearson_exact'if p_exact is not None else'fixed_margin_Pearson_MC'})
    adjust(associations)
    rank_results=[]
    for index,(left,right)in enumerate(plan.get('rank_pairs',[])):
        lc=plan['ordinal'][left];rc=plan['ordinal'][right];pairs=[(lc.index(r['answers'][left])+1,rc.index(r['answers'][right])+1)for r in rows if r['answers'].get(left)in lc and r['answers'].get(right)in rc]
        if len(pairs)<3:rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':None,'p':None,'status':'insufficient_pairs'});continue
        a,b=np.array(pairs).T;a=rankdata(a);b=rankdata(b);a-=a.mean();b-=b.mean();den=np.linalg.norm(a)*np.linalg.norm(b)
        if den==0:rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':None,'p':None,'status':'constant'});continue
        rho=float(a@b/den);rng=np.random.default_rng(seed+100+index);extreme=0;batch=B if B*len(b)<=2000000 else max(1,2000000//len(b))
        for start in range(0,B,batch):
            permuted=rng.permuted(np.broadcast_to(b,(min(batch,B-start),len(b))),axis=1);null=permuted@a/den;extreme+=int(sum(np.abs(null)>=abs(rho)-1e-12))
        p=(extreme+1)/(B+1)
        rank_results.append({'left':left,'right':right,'n':len(pairs),'rho':rho,'p':p,'status':'estimated','resamples':B,'seed':seed+100+index})
    adjust(rank_results)
    multi=[];pairs=[]
    for qid in plan.get('multiple',[]):
        q=qs[qid]
        if q['type']!='multiple' or outcome_conditioned(q):raise ValueError('Do not compare outcome-conditioned multiple responses against their own outcome')
        accepted=[(r,int(yy))for r,yy in zip(cohort,y)if applicable(r,q)and not missing_answer(q,r['answers'].get(qid))and isinstance(r['answers'].get(qid),list)];positive=sum(yy for r,yy in accepted);negative=len(accepted)-positive;family=[]
        for option in q['options']:
            code=option['id'];a=sum(yy==1 and code in r['answers'][qid]for r,yy in accepted);c=sum(yy==0 and code in r['answers'][qid]for r,yy in accepted);b=positive-a;d=negative-c
            family.append({'question':qid,'option':code,'label':option['label'],'paid_selected':a,'paid_n':positive,'free_selected':c,'free_n':negative,'paid_pct':100*a/positive if positive else None,'free_pct':100*c/negative if negative else None,'difference_pp':100*(a/positive-c/negative)if positive and negative else None,'binary_cohort_n':n,'excluded_missing_or_skip':n-len(accepted),**exact(a,b,c,d)})
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
    return clean({'cohort_summary':[{'records':len(rows),'binary_n':n,'positive':int(y.sum()),'negative':int(n-y.sum()),'excluded_outcome':len(rows)-n,'source':rows[0].get('source')}],'measurement_profile':profile,'ordinal_summary':ordinal,'binary_contrasts':contrasts,'group_cells':group_cells,'group_permutation':associations,'rank_permutation':rank_results,'multiple_contrasts':multi,'cooccurrence':pairs,'logistic_models':models,'loo_validation':validation,'conditional_price':price})

def summary_markdown(content):
    """A readable companion to the CSVs, never a claim that final prose is done."""
    titles={'cohort_summary':'分析样本','measurement_profile':'变量与缺失诊断','ordinal_summary':'有序题分布','binary_contrasts':'二元比较与条件OR','group_cells':'画像分组原始计数','group_permutation':'画像组间比较','rank_permutation':'秩关联与重排','multiple_contrasts':'多选题比较','cooccurrence':'多选题共现','logistic_models':'简约二元Logit','loo_validation':'留一概率验证','conditional_price':'条件金额描述'}
    columns={
      'cohort_summary':['records','binary_n','positive','negative','excluded_outcome'],
      'measurement_profile':['question','type','applicable_n','valid_n','structural_skip','missing','distinct_answers','modal_pct','constant'],
      'ordinal_summary':['question','valid_n','q25','median','q75','code_min','code_max','top_two_pct','normalized_entropy'],
      'binary_contrasts':['question','label','exposed_positive','exposed_negative','reference_positive','reference_negative','or_conditional','or_low','or_high','p','p_holm'],
      'group_cells':['dimension','label','n','positive','negative','positive_pct','eligible_n'],
      'group_permutation':['dimension','groups','n','events','excluded_group_missing','chi2','cramers_v','p','p_holm','status'],
      'rank_permutation':['left','right','n','rho','p','p_holm','status'],
      'multiple_contrasts':['question','label','paid_selected','paid_n','free_selected','free_n','paid_pct','free_pct','difference_pp','p','p_holm'],
      'cooccurrence':['question','one_label','two_label','n','both','one_only','two_only','neither','jaccard','lift'],
      'logistic_models':['question','events','mle_finite','mle_or','mle_or_wald_low','mle_or_wald_high','firth_or'],
      'loo_validation':['model','n','events','brier','log_loss','positive_recall','specificity','balanced_accuracy'],
      'conditional_price':['group','n','min','q25','median','q75','max','mean']}
    labels={'records':'记录数','binary_n':'二元结局有效数','positive':'正向','negative':'负向','excluded_outcome':'未纳入结局分析','question':'题号','type':'题型','applicable_n':'适用数','valid_n':'有效数','structural_skip':'跳题数','missing':'缺失数','distinct_answers':'不同回答数','modal_pct':'众数占比%','constant':'常量','label':'组别/选项','dimension':'画像维度','n':'有效n','eligible_n':'该维度有效n','groups':'有效组数','events':'正向记录数','excluded_group_missing':'画像缺失数','positive_pct':'正向比例%','paid_selected':'正向选中','paid_n':'正向有效n','free_selected':'负向选中','free_n':'负向有效n','paid_pct':'正向选中%','free_pct':'负向选中%','difference_pp':'比例差/百分点','status':'计算状态','model':'模型','mle_finite':'MLE有限','firth_or':'Firth OR','left':'题号1','right':'题号2','one_label':'选项1','two_label':'选项2','both':'同时选择','one_only':'只选1','two_only':'只选2','neither':'均未选','group':'组别'}
    notes={'binary_contrasts':'两侧Fisher p值、条件OR及其95%精确区间分别报告；校正按本表有效比较家族。',
      'group_cells':'各画像维度单独保留有效分母；缺失画像不补作任何已知组别。',
      'group_permutation':'采用固定边际、Pearson统计量排序的条件检验；完整CSV含精确枚举或重排定义、种子、次数及Monte Carlo误差。',
      'multiple_contrasts':'各选项采用两侧Fisher检验，按该题有效比较进行Holm校正。百分比分母为该题实际有效的正向/负向记录数；空组比例和检验保持未定义。paid/free为兼容字段名，在此按分析计划的正向/负向解释。',
      'logistic_models':'每个模型只有截距与一个二元预测变量；MLE Wald区间与Firth点估计分列，不将Wald区间归给Firth。',
      'loo_validation':'各折排除该记录结局后重拟合；对照截距基线，概率损失与少数类/平衡指标同时核对。'}
    def cell(value):
        if value is None:return '—'
        if isinstance(value,float):return format(value,'.7g')
        return re.sub(r'([\\`*_[\]()|])',r'\\\1',str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\r',' ').replace('\n',' '))
    cohort=content['cohort_summary'][0];source={'ai_synthetic':'AI受访者调研','human_reported':'用户登记回收记录'}[cohort['source']]
    lines=['# 统计结果核对','',f'来源：{source}。分析单位：一条答卷记录。共{cohort["records"]}条，二元结局有效{cohort["binary_n"]}条。','',
      '本文件由同次实际计算生成，供对话与写作流程回读；完整精度、方法字段及文件SHA见CSV、results.json与manifest.json。未定义值记为“—”。','']
    for name,rows in content.items():
        if not rows:continue
        keys=[k for k in columns[name]if any(k in row for row in rows)]
        lines.extend(['## '+titles[name],'',f'结果文件：`{name}.csv`。'+notes.get(name,''),'','| '+' | '.join(labels.get(k,k)for k in keys)+' |','| '+' | '.join('---'for k in keys)+' |'])
        lines.extend('| '+' | '.join(cell(row.get(k))for k in keys)+' |'for row in rows);lines.append('')
    return '\n'.join(lines)

def run(questionnaire,data,plan,out,overwrite=False):
    out=Path(out);snapshots={label:Path(file).read_bytes()for label,file in [('questionnaire',questionnaire),('data',data),('plan',plan)]};inputs={label:hashlib.sha256(value).hexdigest()for label,value in snapshots.items()};documents={label:json.loads(value.decode('utf-8-sig'))for label,value in snapshots.items()}
    previous=None
    if out.exists()and any(out.iterdir()):
        if not overwrite:raise ValueError('Choose a new output directory or explicitly permit verified generated-file replacement')
        previous=json.loads((out/'manifest.json').read_text(encoding='utf8'))
        if previous['input_sha256']!=inputs:raise ValueError('Inputs changed; preserve this version and use a new directory')
        for f in previous['files']:
            if sha(out/f['path'])!=f['sha256']:raise ValueError('Generated file was edited; preserve it and use a new directory')
    content=tables(documents['questionnaire'],documents['data'],documents['plan'])
    out.mkdir(parents=True,exist_ok=True);files=[]
    def register(p):files.append({'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size})
    for name,rows in content.items():
        if not rows:continue
        p=out/(name+'.csv');keys=list(dict.fromkeys(k for row in rows for k in row))
        with p.open('w',encoding='utf-8-sig',newline='')as f:
            safe=lambda v:"'"+v if isinstance(v,str)and v.lstrip().startswith(('=','+','-','@','\t','\r'))else v
            w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:safe(v)for k,v in row.items()}for row in rows)
        register(p)
    p=out/'results.json';p.write_text(json.dumps({'input_sha256':inputs,'analysis':content,'source':documents['data'].get('source'),'inference_scope':'Exploratory record-structure diagnostics under stated reference models; no causal or population claim','software':{k:importlib.metadata.version(k)for k in ['numpy','scipy']}},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');register(p)
    p=out/'summary.md';p.write_text(summary_markdown(content),encoding='utf8');register(p)
    (out/'manifest.json').write_text(json.dumps({'schema':2,'analysis_unit':'one_record_per_response','record_source':content['cohort_summary'][0]['source'],'input_sha256':inputs,'program_sha256':sha(__file__),'files':files},ensure_ascii=False,indent=2),encoding='utf8')
    return {'tables':sum(f['path'].endswith('.csv')for f in files),'rows':{k:len(v)for k,v in content.items()},'summary':str(out/'summary.md'),'output':str(out)}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--questionnaire',required=True);p.add_argument('--data',required=True);p.add_argument('--plan',required=True);p.add_argument('--out',required=True);p.add_argument('--overwrite-generated',action='store_true');a=p.parse_args();print(json.dumps(run(a.questionnaire,a.data,a.plan,a.out,a.overwrite_generated),ensure_ascii=False))
