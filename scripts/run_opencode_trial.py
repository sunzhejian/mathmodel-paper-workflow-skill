"""Optional one-session OpenCode Chat/Responses trial; no direct API or key storage."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
try:
    from run_codex_trial import route_config,redacted
except ImportError:
    from scripts.run_codex_trial import route_config,redacted


def tool_config(cfg: dict, output_tokens: int, effort: str | None = None, project_tools: dict | None = None, protocol: str = 'chat') -> dict:
    if protocol not in {'chat','responses'}:raise ValueError('Select chat or responses protocol explicitly')
    model=cfg['model']
    model_options={'reasoningEffort':effort} if effort else {}
    config={'$schema':'https://opencode.ai/config.json','enabled_providers':['trial'],
            'model':'trial/'+model,'small_model':'trial/'+model,'share':'disabled','autoupdate':False,
            'permission':{'*':'deny'},'mcp':{},
            'provider':{'trial':{'npm':'@ai-sdk/openai' if protocol=='responses' else '@ai-sdk/openai-compatible','name':'Anonymous trial',
                               'options':{'baseURL':cfg['base_url'],'apiKey':'{env:'+cfg['env_key']+'}','timeout':480000},
                               'models':{model:{'name':model,'options':model_options,'limit':{'context':256000,'output':output_tokens}}}}}}
    if project_tools is not None:
        if set(project_tools)!={'name','command'} or project_tools['name'] not in {'paper_project','case_materials','workflow_project'}:raise ValueError('Only reviewed paper_project, case_materials or workflow_project interfaces are supported')
        command=project_tools['command']
        if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command):raise ValueError('Expected explicit project tool command arguments')
        interface=project_tools['name']
        config['mcp']={interface:{'type':'local','command':command,'enabled':True,'timeout':120000}}
        config['permission'][interface+'_*']='allow'
    return config


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


def run_trial(cli: str,cfg: dict,prompt: Path,output: Path,output_tokens: int, effort: str | None = None, project_tools: dict | None = None, protocol: str = 'chat') -> dict:
    secret=os.environ.get(cfg['env_key'],'')
    if not secret:raise ValueError('Credential environment variable missing')
    raw=prompt.read_bytes()
    if secret in raw.decode('utf-8') or any(secret in x for x in cfg.values()):raise ValueError('Credential found in public inputs')
    if project_tools and secret in json.dumps(project_tools):raise ValueError('Credential found in project tool arguments')
    if effort not in {None,'low','medium','high'}:raise ValueError('Unsupported reasoning option')
    config=tool_config(cfg,output_tokens,effort,project_tools,protocol)
    output.mkdir(parents=True,exist_ok=False)
    output=output.resolve()
    env=os.environ.copy()
    env['OPENCODE_CONFIG_CONTENT']=json.dumps(config)
    env['OPENCODE_DISABLE_AUTOUPDATE']='true'
    env['OPENCODE_DISABLE_SESSION_SHARING']='true'
    # Each CLI gets its own database/cache; concurrent runs must not share a
    # global SQLite migration lock or affect the user's ordinary OpenCode state.
    for kind in ['DATA','CONFIG','CACHE','STATE']:
        env['XDG_'+kind+'_HOME']=str(output/'.opencode'/kind.lower())
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
    answer_path=output/('answer.txt' if project_tools else 'answer.json')
    if answer:answer_path.write_bytes(answer.encode('utf-8'))
    pseudo_tool_text=bool(re.search(r'<(?:seed:tool_call|tool_call|function\s+name=)|anomalyBashParam',answer))
    report={'tool':'OpenCode','model':cfg['model'],'base_url':cfg['base_url'],'protocol':'Responses' if protocol=='responses' else 'Chat Completions','reasoning_effort':effort or 'provider-default','effort_scope':'client configuration; provider behavior is not independently verified','isolated_client_state':True,
            'mode':({'case_materials':'case-materials-task','paper_project':'project-tool-task','workflow_project':'workflow-project-task'}[project_tools['name']]) if project_tools else 'text-only',
            'selected_tool_interface':project_tools['name'] if project_tools else None,
            'configured_output_tokens':output_tokens,'prompt_sha256':hashlib.sha256(raw).hexdigest(),'exit_code':proc.returncode,
            'timed_out':timed_out,'seconds':round(time.monotonic()-started,1),'answer_present':bool(answer),'complete_stop_event':finished,
            'tool_events':tools,'events':events,'stderr_tail':redacted(stderr,secret)[-1200:],
            'simulated_tool_call_text_detected':pseudo_tool_text,
            'unexecuted_tool_intent':pseudo_tool_text and tools==0,
            'task_accepted':False,'acceptance_scope':'Client completion is separate from verified task/artifact acceptance; text resembling a tool call is not execution'}
    if answer:report['answer_sha256']=hashlib.sha256(answer_path.read_bytes()).hexdigest()
    report['successful_session']=proc.returncode==0 and not timed_out and bool(answer) and finished
    report['answer_delivery_valid']=report['successful_session'] and not report['unexecuted_tool_intent']
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
    p.add_argument('--effort',choices=['low','medium','high'])
    p.add_argument('--protocol',choices=['chat','responses'],default='chat')
    p.add_argument('--project-tools',type=Path,help='Reviewed project or read-only material/workflow MCP name/command JSON; no secrets')
    args=p.parse_args()
    try:
        if not args.opencode or not 1000<=args.output_tokens<=32000:raise ValueError('Unavailable CLI or unsupported trial output budget')
        project_tools=json.loads(args.project_tools.read_text(encoding='utf-8')) if args.project_tools else None
        r=run_trial(args.opencode,route_config(args.routes,args.route),args.prompt,args.output,args.output_tokens,args.effort,project_tools,args.protocol)
        print(json.dumps({k:r[k] for k in ['tool','model','exit_code','timed_out','seconds','answer_present','complete_stop_event','tool_events']}))
        return 0 if r['answer_delivery_valid'] else 1
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'error_type':type(exc).__name__,'successful_session':False}))
        return 2


if __name__=='__main__':raise SystemExit(main())
