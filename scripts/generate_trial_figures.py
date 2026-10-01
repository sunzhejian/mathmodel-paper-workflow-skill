"""Create editable README figures from the saved model-trial evidence.

Uses standard library for .drawio and JSON. --render additionally needs an
existing draw.io desktop CLI. No AI requests or credentials are used.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE=ROOT/'examples/model-trials/observed-v2/evaluation.json'


def input_key(case: dict) -> tuple[str,...]:
    # Equivalent rational spellings are one executed input, independent of the
    # report, round label, nominal/endpoint name, or display representation.
    return tuple(str(Fraction(str(x))) for x in [*case['arguments'],case['cost_expression']])


def distinct_cases(checks: dict, names: list[str]) -> dict:
    if len({checks[name].get('source_sha256') for name in names})!=1:
        raise ValueError('Do not combine executions of different solver source versions')
    inputs={}
    for name in names:
        for case in checks[name]['cases']:
            key=input_key(case)
            inputs[key]=inputs.get(key,True) and case['matches_reference']
    return {'passed':sum(inputs.values()),'total':len(inputs)}


def summarize(evidence: dict) -> dict:
    checks=evidence['maintainer_execution_and_compile_checks']
    records={x['id']:x for x in evidence['records']}
    original=checks['deepseek_new_code']
    repaired=checks['deepseek_repair_probes']
    if {input_key(x) for x in original['cases']}!={input_key(x) for x in repaired['cases']}:
        raise ValueError('Before/after comparison must use the same input set')
    old_keys={input_key(x) for x in repaired['cases']}
    unseen=[x for x in checks['deepseek_repair_unseen']['cases'] if input_key(x) not in old_keys]
    models=[]
    for name,record,code_keys,latex_key in [
        ('DeepSeek','deepseek-new',['deepseek_repair_probes','deepseek_repair_unseen'],'deepseek_new_latex'),
        ('GLM','glm-assembled',['glm_code_probes','glm_unseen'],'glm_latex'),
        ('Kimi','kimi-new',['kimi_new_code','kimi_unseen'],'kimi_new_latex')]:
        numeric=records[record]['numeric_shape_checks']
        models.append({'name':name,'numeric':{'passed':numeric['passed'],'total':numeric['total']},
                       'numeric_scope':'分阶段旧题' if name=='GLM' else '新参数任务',
                       'code':distinct_cases(checks,code_keys),'latex_pass':checks[latex_key].get('compile_and_width_checks_pass',False),
                       'note':{'DeepSeek':'代码已修复；原文字仍需审查','GLM':'新参数整包超时，未计通过','Kimi':'通过项限于本轮测试范围'}[name]})
    return {'date':evidence['date'],'sessions':evidence['sessions_requested'],
            'completed_original_answers':sum(bool(r.get('raw_file')) for r in evidence['records']),
            'failed_sessions':len(evidence['failed_sessions']),'models':models,
            'repair':{'before':{'passed':original['passed'],'total':original['total']},
                      'after_same_inputs':{'passed':repaired['passed'],'total':repaired['total']},
                      'new_inputs':{'passed':sum(x['matches_reference'] for x in unseen),'total':len(unseen)},
                      'all_distinct':distinct_cases(checks,['deepseek_repair_probes','deepseek_repair_unseen'])}}


class Figure:
    def __init__(self,title,width,height):
        self.width=width;self.height=height
        self.doc=ET.Element('mxfile',host='app.diagrams.net')
        diagram=ET.SubElement(self.doc,'diagram',id='trial-figure',name=title)
        model=ET.SubElement(diagram,'mxGraphModel',page='1',pageWidth=str(width),pageHeight=str(height),grid='0',background='#ffffff')
        self.root=ET.SubElement(model,'root')
        ET.SubElement(self.root,'mxCell',id='0')
        ET.SubElement(self.root,'mxCell',id='1',parent='0')
        self.used=set()
        self.box('canvas','',0,0,width,height,fill='#FFFFFF',size=24)

    def box(self,key,text,x,y,w,h,fill='none',size=28,bold=False,color='#20324A',align='left'):
        if key in self.used:raise ValueError('Duplicate figure id')
        self.used.add(key)
        size=48 if size>=40 else 32 if size>=28 else 24
        value='<br>'.join(html.escape(line) for line in text.split('\n'))
        style=f'rounded=0;whiteSpace=wrap;html=1;align={align};verticalAlign=middle;spacing=0;strokeColor=none;fillColor={fill};fontSize={size};fontStyle={int(bold)};fontFamily=Microsoft YaHei;fontColor={color};'
        if fill=='none':style='text;'+style
        cell=ET.SubElement(self.root,'mxCell',id=key,value=value,style=style,vertex='1',parent='1')
        ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})

    def arrow(self,key,x1,y1,x2,y2):
        cell=ET.SubElement(self.root,'mxCell',id=key,style='edgeStyle=none;html=1;endArrow=block;endFill=1;strokeColor=#536B89;strokeWidth=2;endSize=10;',edge='1',parent='1')
        geo=ET.SubElement(cell,'mxGeometry',relative='1',**{'as':'geometry'})
        ET.SubElement(geo,'mxPoint',x=str(x1),y=str(y1),**{'as':'sourcePoint'})
        ET.SubElement(geo,'mxPoint',x=str(x2),y=str(y2),**{'as':'targetPoint'})

    def save(self,path):
        ET.indent(self.doc)
        ET.ElementTree(self.doc).write(path,encoding='utf-8',xml_declaration=True)


def overview(data: dict) -> Figure:
    f=Figure('真实模型测试结果',1600,980)
    f.box('title','真实模型测试示例',56,42,1488,76,size=48,bold=True)
    f.box('subtitle',f"DeepSeek · GLM · Kimi  /  {data['date']}  /  匿名合成任务",56,124,1488,46,size=26,color='#62738A')
    for i,(value,label) in enumerate([(data['sessions'],'次会话'),(data['completed_original_answers'],'份原始答复'),(data['failed_sessions'],'次截断或超时')]):
        x=56+i*506
        f.box(f'badge_bg_{i}','',x,196,476,62,fill='#EAF0F8')
        f.box(f'badge_{i}',f'{value} {label}',x+22,206,432,42,size=28,bold=True)
    for i,m in enumerate(data['models']):
        x=56+i*506
        f.box(f'card_bg_{i}','',x,292,476,524,fill='#F5F8FC')
        f.box(f'accent_{i}','',x,292,476,7,fill='#2C507A')
        f.box(f'model_{i}',m['name'],x+26,318,424,58,size=40,bold=True)
        f.box(f'scope_{i}',m['numeric_scope'],x+26,376,424,35,size=23,color='#62738A')
        f.box(f'numeric_label_{i}','数值与字段检查',x+26,432,424,34,size=24)
        n=m['numeric']
        f.box(f'numeric_value_{i}',f"{n['passed']} / {n['total']}",x+26,470,424,58,size=40,bold=True,color='#2C507A')
        c=m['code']
        code_label=['修复后程序 · 输入去重','旧题通用程序 · 输入去重','新参数程序 · 输入去重'][i]
        f.box(f'code_label_{i}',code_label,x+26,550,424,34,size=24)
        f.box(f'code_value_{i}',f"{c['passed']} / {c['total']} 个输入通过",x+26,590,424,48,size=29,bold=True)
        f.box(f'latex_label_{i}','公式片段 · 实际编译',x+26,660,424,34,size=24)
        f.box(f'latex_value_{i}','通过' if m['latex_pass'] else '未通过',x+26,700,424,42,size=29,bold=True,color='#2C507A')
        f.box(f'note_{i}',m['note'],x+26,764,424,35,size=21,color='#896020' if i<2 else '#62738A')
    f.box('note1','GLM显示旧题分阶段结果；新参数完整会话未完成。超时与截断不计作通过。',56,850,1488,42,size=24)
    f.box('note2','仅为列明小任务的验证记录，不是模型排行榜，也不代表完整论文质量。',56,904,1488,38,size=24,color='#62738A')
    return f


def repair_flow(data: dict) -> Figure:
    f=Figure('程序错误修复与复测',1600,860)
    r=data['repair'];before=r['before'];after=r['after_same_inputs'];new=r['new_inputs'];total=r['all_distinct']
    f.box('title','从实际错误到可复验修复',56,40,1488,75,size=48,bold=True)
    f.box('subtitle','示例：连续吨数错用整数上取整技巧，造成可行运输方案漏算',56,124,1488,44,size=26,color='#62738A')
    cols=[56,562,1068]
    blocks=[
        ('01  发现错误',f"{before['passed']} / {before['total']}",'原程序 · 同一组输入','3个非整数质量输入失败\n检查实际输出，不靠自评'),
        ('02  模型修复',f"{after['passed']} / {after['total']}",'修复后 · 原有输入','只给1个失败输入和源码\n改为适用分数的上取整'),
        ('03  新输入复测',f"{new['passed']} / {new['total']}",'未放入修复提示的输入','新增350kg、275kg运力\n结合非整数吨数再次验证')]
    for i,(title,value,label,body) in enumerate(blocks):
        x=cols[i]
        f.box(f'bg_{i}','',x,222,476,346,fill='#F5F8FC')
        f.box(f'head_{i}',title,x+26,244,424,48,size=31,bold=True)
        f.box(f'value_{i}',value,x+26,310,424,66,size=46,bold=True,color='#2C507A')
        f.box(f'label_{i}',label,x+26,385,424,38,size=24,color='#62738A')
        f.box(f'body_{i}',body,x+26,449,424,85,size=25)
    f.arrow('edge_1',534,394,560,394)
    f.arrow('edge_2',1040,394,1066,394)
    f.box('summary_bg','',56,608,1488,108,fill='#EAF0F8')
    f.box('summary',f"去重后共 {total['total']} 种输入通过：8个题内案例 + 3个原探针 + {new['total']} 个新探针",82,622,1436,75,size=29,bold=True)
    f.box('scope','原有11个输入前后对照；新增输入单列。原始失败和修复答复分别保留。',56,746,1488,42,size=24)
    f.box('scope2','这一轮结果支持被测输入下的修复效果，不证明任意输入或整篇论文都正确。',56,798,1488,34,size=24,color='#62738A')
    return f


def generate(evidence_path: Path,output: Path) -> dict:
    raw=evidence_path.read_bytes()
    data=summarize(json.loads(raw))
    data['source_sha256']=hashlib.sha256(raw).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    for stem,figure in [('04-model-trial-results',overview(data)),('05-code-repair-example',repair_flow(data))]:
        figure.save(output/(stem+'.drawio'))
    (output/'model-trials-summary.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    return data


def render(output: Path,cli: str) -> None:
    for stem in ['04-model-trial-results','05-code-repair-example']:
        src=output/(stem+'.drawio')
        for ext in ['png','svg','pdf']:
            args=[cli,'-x','-f',ext,'-o',str(src.with_suffix('.'+ext)),str(src)]
            if ext=='png':args[4:4]=['--width','1600','-b','0']
            if ext=='pdf':args[4:4]=['--crop']
            result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            if result.returncode or not src.with_suffix('.'+ext).exists():raise RuntimeError('draw.io export failed: '+stem+'.'+ext)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=DEFAULT_EVIDENCE)
    p.add_argument('--output',type=Path,default=ROOT/'docs/figures')
    p.add_argument('--render',action='store_true')
    p.add_argument('--drawio',default=shutil.which('draw.io') or shutil.which('drawio'))
    a=p.parse_args()
    data=generate(a.evidence,a.output)
    if a.render:
        if not a.drawio:raise SystemExit('Existing draw.io CLI required for export')
        render(a.output,a.drawio)
    print(json.dumps({'distinct_inputs':[m['code']['total'] for m in data['models']],'sessions':data['sessions'],'rendered':a.render}))
    return 0


if __name__=='__main__':raise SystemExit(main())
