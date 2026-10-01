"""Compile manually reviewed anonymous LaTeX body fragments as a layout fixture.

This is not a TeX security sandbox or a full-paper verifier. Never compile
unreviewed generated source. The output directory must be new.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

try:
    from model_trial import parse_answer
except ImportError:
    from scripts.model_trial import parse_answer

FORBIDDEN=re.compile(r'\\(?:input|include|includegraphics|openin|openout|read|write|csname|usepackage|documentclass|special|directlua)(?![A-Za-z])',re.IGNORECASE)


def body_source(answer: dict, margin: float) -> str:
    pieces=[]
    for key,title in [('transport','Transport model'),('inference','Latent-share model')]:
        fragment=answer.get(key,{}).get('latex_model')
        if not isinstance(fragment,str) or not fragment.strip():
            raise ValueError('Both model fragments must be present')
        if FORBIDDEN.search(fragment):
            raise ValueError('External I/O, dynamic commands or full-document source found; review outside this helper')
        pieces.append(r'\section*{'+title+'}\n'+fragment)
    return (r'\documentclass[12pt]{article}'+'\n'+
            r'\usepackage[a4paper,margin='+str(margin)+r'cm]{geometry}'+'\n'+
            r'\usepackage{amsmath,amssymb}'+'\n'+r'\begin{document}'+'\n'+
            '\n'.join(pieces)+'\n'+r'\end{document}'+'\n')


def log_checks(log: str) -> dict:
    overfull=re.findall(r'Overfull \\[hv]box[^\n]*',log)
    missing=[line for line in log.splitlines() if 'Missing character:' in line]
    errors=[line for line in log.splitlines() if line.startswith('!')]
    return {'overfull':overfull,'missing_characters':missing,'latex_errors':errors[:10],'undefined_control_sequence':'Undefined control sequence' in log}


def compile_fragments(answer_path: Path, output: Path, compiler: str, margin: float, render: bool) -> dict:
    raw=answer_path.read_bytes()
    answer=parse_answer(raw.decode('utf-8'))
    text=body_source(answer,margin)
    output.mkdir(parents=True,exist_ok=False)
    source=output/'formulas.tex'
    source.write_text(text,encoding='utf-8')
    command=[compiler,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','formulas.tex']
    # Compiler receives no provider credential environment variables.
    import os
    env={k:v for k,v in os.environ.items() if k.upper() in ['PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA']}
    proc=subprocess.Popen(command,cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
    timed_out=False
    try:stdout,stderr=proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        timed_out=True
        proc.kill()
        stdout,stderr=proc.communicate()
    log=stdout+stderr
    (output/'compile.txt').write_text(log,encoding='utf-8')
    result={'answer_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'fixture':{'paper':'A4','font_pt':12,'margin_cm':margin},'compile_exit_code':proc.returncode,'timed_out':timed_out,**log_checks(log)}
    pdf=output/'formulas.pdf'
    result['pdf_present']=pdf.exists()
    if proc.returncode==0 and not timed_out and pdf.exists():
        import pymupdf
        with pymupdf.open(pdf) as document:
            result['page_count']=len(document)
            if render:
                for idx,page in enumerate(document):
                    page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(str(output/f'page-{idx+1}.png'))
                result['rendered_pages']=len(document)
        result['pdf_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest()
    result['compile_and_width_checks_pass']=(proc.returncode==0 and not timed_out and pdf.exists() and not result['overfull'] and not result['missing_characters'] and not result['undefined_control_sequence'])
    result['limits']='Actual compilation and log-based width/character checks only; source was reviewed separately. Math, overlap, full-paper layout and contest compliance require separate review.'
    (output/'check.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compiler',default=shutil.which('xelatex'))
    parser.add_argument('--margin-cm',type=float,default=2.5)
    parser.add_argument('--reviewed-source',action='store_true',help='Use only after actually reading the generated source')
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    try:
        if not args.reviewed_source:raise ValueError('Review source before compilation; no compiler invoked')
        if not args.compiler:raise ValueError('XeLaTeX unavailable; no compile success can be claimed')
        if not 0<args.margin_cm<8:raise ValueError('Invalid fixture margin')
        result=compile_fragments(args.answer,args.output,args.compiler,args.margin_cm,args.render)
        print(json.dumps({k:result[k] for k in ['compile_exit_code','timed_out','overfull','missing_characters','compile_and_width_checks_pass']}))
        return 0 if result['compile_and_width_checks_pass'] else 1
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc),'compile_and_width_checks_pass':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
