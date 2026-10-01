"""Merge completed, matching context-only trial stages, retaining provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
try:
    from model_trial import parse_answer
except ImportError:
    from scripts.model_trial import parse_answer


def read_stage(directory: Path, part: str) -> tuple[dict,dict,dict]:
    manifest=json.loads((directory.parent/'manifest.json').read_text(encoding='utf-8'))
    run=json.loads((directory/'run.json').read_text(encoding='utf-8'))
    if manifest.get('part')!=part:
        raise ValueError('Stage role does not match its manifest')
    if run.get('exit_code')!=0 or run.get('timed_out') or not run.get('answer_present') or run.get('tool_events')!=0:
        raise ValueError('Only completed context-only stages can be merged')
    if run.get('successful_session') is False or run.get('complete_stop_event') is False:
        raise ValueError('The client did not receive a complete answer')
    raw=(directory/'answer.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=run.get('answer_sha256'):
        raise ValueError('Answer changed after the run report')
    prompt=(directory.parent/'prompt.txt').read_bytes()
    if hashlib.sha256(prompt).hexdigest()!=run.get('prompt_sha256'):
        raise ValueError('Prompt changed after the stage')
    answer=parse_answer(raw.decode('utf-8'))
    run['answer_fence_removed']=raw.decode('utf-8').lstrip().startswith('```')
    if not isinstance(answer,dict) or set(answer)!={part} or not isinstance(answer[part],dict):
        raise ValueError('Stage must contain only its named task object')
    return answer,manifest,run


def merge(transport: Path, inference: Path, output: Path) -> dict:
    a,ma,ra=read_stage(transport,'transport')
    b,mb,rb=read_stage(inference,'inference')
    for key in ['round','task_schema_version','task_sha256','context_sha256']:
        if ma.get(key)!=mb.get(key):raise ValueError('Stages have different task or skill snapshots')
    for key in ['model','base_url','reasoning_effort','tool']:
        if ra.get(key)!=rb.get(key):raise ValueError('Stages have different model or request configuration')
    output.mkdir(parents=True,exist_ok=False)
    answer_path=output/'answer.json'
    answer_path.write_text(json.dumps({**a,**b},indent=2,ensure_ascii=False),encoding='utf-8')
    report={'round':ma['round'],'model':ra['model'],'task_sha256':ma['task_sha256'],'context_sha256':ma['context_sha256'],
            'source_answer_sha256':[ra['answer_sha256'],rb['answer_sha256']],
            'source_prompt_sha256':[ra['prompt_sha256'],rb['prompt_sha256']],
            'source_fence_removed':[ra['answer_fence_removed'],rb['answer_fence_removed']],
            'merged_answer_sha256':hashlib.sha256(answer_path.read_bytes()).hexdigest(),
            'source_sessions':2,'numeric_checks_executed':False,'code_executed':False,'latex_compiled':False,
            'scope':'Mechanical assembly only; original stage files are unchanged. No science or execution claim.'}
    (output/'merge.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport',type=Path,required=True)
    p.add_argument('--inference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        result=merge(args.transport,args.inference,args.output)
        print(json.dumps(result))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc),'merged':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
