"""Optional one-session OpenCode Chat-API trial; no direct API or key storage."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
try:
    from run_codex_trial import route_config,redacted
except ImportError:
    from scripts.run_codex_trial import route_config,redacted


def tool_config(cfg: dict, output_tokens: int) -> dict:
    model=cfg['model']
    return {'$schema':'https://opencode.ai/config.json','enabled_providers':['trial'],
            'model':'trial/'+model,'small_model':'trial/'+model,'share':'disabled','autoupdate':False,
            'permission':{'*':'deny'},'mcp':{},
            'provider':{'trial':{'npm':'@ai-sdk/openai-compatible','name':'Anonymous trial',
                               'options':{'baseURL':cfg['base_url'],'apiKey':'{env:'+cfg['env_key']+'}','timeout':480000},
                               'models':{model:{'name':model,'limit':{'context':256000,'output':output_tokens}}}}}}


def collect_events(stdout: str, secret: str) -> tuple[str,list[dict],int,bool]:
    text=[]
    events=[]
    tools=0
    finished=False
    for line in stdout.splitlines():
        try:e=json.loads(line)
        except ValueError:continue
        if not isinstance(e,dict):continue
        if e.get('type')=='text':
            part=e.get('part',{})
            if isinstance(part,dict) and isinstance(part.get('text'),str):text.append(part['text'])
        elif e.get('type')=='tool_use':tools+=1
        elif e.get('type')=='step_finish':
            part=e.get('part',{})
            events.append({'type':'step_finish','reason':part.get('reason'),'tokens':part.get('tokens')})
            finished=part.get('reason')=='stop'
        elif e.get('type')=='error':
            events.append({'type':'error','message':redacted(str(e.get('error','')),secret)[:1000]})
    return redacted(''.join(text),secret),events,tools,finished


def run_trial(cli: str,cfg: dict,prompt: Path,output: Path,output_tokens: int) -> dict:
    secret=os.environ.get(cfg['env_key'],'')
    if not secret:raise ValueError('Credential environment variable missing')
    raw=prompt.read_bytes()
    if secret in raw.decode('utf-8') or any(secret in x for x in cfg.values()):raise ValueError('Credential found in public inputs')
    config=tool_config(cfg,output_tokens)
    output.mkdir(parents=True,exist_ok=False)
    output=output.resolve()
    env=os.environ.copy()
    env['OPENCODE_CONFIG_CONTENT']=json.dumps(config)
    env['OPENCODE_DISABLE_AUTOUPDATE']='true'
    env['OPENCODE_DISABLE_SESSION_SHARING']='true'
    args=[cli,'run','--pure','--format','json','--model','trial/'+cfg['model'],'--title','Anonymous model trial','--dir',str(output)]
    started=time.monotonic()
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env=env)
    timed_out=False
    try:stdout,stderr=proc.communicate(raw.decode('utf-8'),timeout=480)
    except subprocess.TimeoutExpired:
        timed_out=True
        proc.kill()
        stdout,stderr=proc.communicate()
    answer,events,tools,finished=collect_events(stdout,secret)
    if answer:(output/'answer.json').write_bytes(answer.encode('utf-8'))
    report={'tool':'OpenCode','model':cfg['model'],'base_url':cfg['base_url'],'protocol':'Chat Completions','reasoning_effort':'provider-default',
            'configured_output_tokens':output_tokens,'prompt_sha256':hashlib.sha256(raw).hexdigest(),'exit_code':proc.returncode,
            'timed_out':timed_out,'seconds':round(time.monotonic()-started,1),'answer_present':bool(answer),'complete_stop_event':finished,
            'tool_events':tools,'events':events,'stderr_tail':redacted(stderr,secret)[-1200:]}
    if answer:report['answer_sha256']=hashlib.sha256((output/'answer.json').read_bytes()).hexdigest()
    report['successful_session']=proc.returncode==0 and not timed_out and bool(answer) and finished
    (output/'run.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--routes',type=Path,required=True)
    p.add_argument('--route',required=True)
    p.add_argument('--prompt',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--opencode',default=shutil.which('opencode.exe') or shutil.which('opencode'))
    p.add_argument('--output-tokens',type=int,default=32000)
    args=p.parse_args()
    try:
        if not args.opencode or not 1000<=args.output_tokens<=32000:raise ValueError('Unavailable CLI or unsupported trial output budget')
        r=run_trial(args.opencode,route_config(args.routes,args.route),args.prompt,args.output,args.output_tokens)
        print(json.dumps({k:r[k] for k in ['tool','model','exit_code','timed_out','seconds','answer_present','complete_stop_event','tool_events']}))
        return 0 if r['successful_session'] else 1
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'error_type':type(exc).__name__,'successful_session':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
