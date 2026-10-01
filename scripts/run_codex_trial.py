"""Run one user-authorized anonymous trial with an installed Codex CLI.

No direct API client, key file or paid endpoint fallback. Credentials come from
the configured environment variable; reports omit reasoning text and redact keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import urlsplit


def redacted(text: str, secret: str) -> str:
    text=text.replace(secret,'[REDACTED]') if secret else text
    return re.sub(r'(?:sk-sp-|ark-)[A-Za-z0-9._-]{15,}','[REDACTED]',text)


def safe_events(text: str, secret: str) -> tuple[list[dict],int]:
    events=[]
    tool_count=0
    for line in text.splitlines():
        try: event=json.loads(line)
        except (ValueError,TypeError): continue
        kind=event.get('type')
        item=event.get('item',{})
        if isinstance(item,dict) and item.get('type') in ['command_execution','mcp_tool_call','web_search','file_change']:
            tool_count+=1
        if kind in ['turn.completed','turn.failed','error']:
            # Do not copy full error bodies or chain-of-thought into reports.
            message=str(event.get('message',event.get('error','')))
            events.append({'type':kind,'message':redacted(message,secret)[:1000],'usage':event.get('usage')})
    return events,tool_count


def route_config(path: Path, name: str) -> dict:
    routes=json.loads(path.read_text(encoding='utf-8'))
    cfg=routes[name]
    if not isinstance(cfg,dict) or set(cfg)!={'base_url','model','env_key'}:
        raise ValueError('Route must contain only base_url, model, env_key; never store a key here')
    if not all(isinstance(v,str) and v for v in cfg.values()):
        raise ValueError('Route fields must be non-empty strings')
    url=urlsplit(cfg['base_url'])
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Route requires an HTTPS base URL without credentials/query/fragment')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',cfg['env_key']):
        raise ValueError('Invalid environment variable name')
    return cfg


def run_trial(cli: str, cfg: dict, prompt: Path, output: Path, effort: str, timeout: int) -> dict:
    secret=os.environ.get(cfg['env_key'],'')
    if not secret:
        raise ValueError('Configured credential environment variable is missing; no request made')
    raw=prompt.read_bytes()
    text=raw.decode('utf-8')
    if any(secret in value for value in cfg.values()):
        raise ValueError('Credential detected in route fields; no request made')
    if secret in text or re.search(r'(?:sk-sp-|ark-)[A-Za-z0-9._-]{15,}',text):
        raise ValueError('Credential detected in prompt; no request made')
    # Credentials are already in the host process environment. The CLI consumes
    # them for authentication; model-generated shell commands inherit none.
    provider={'name':'trial','base_url':cfg['base_url'],'env_key':cfg['env_key'],'wire_api':'responses',
              'request_max_retries':0,'stream_max_retries':0,'stream_idle_timeout_ms':120000}
    # Inline TOML strings use JSON escaping, never shell interpolation.
    inline='{'+','.join(k+'='+json.dumps(v) for k,v in provider.items())+'}'
    output.mkdir(parents=True,exist_ok=False)
    output=output.resolve()
    args=[cli,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
          '--sandbox','read-only','--color','never','--json','-C',str(output),'-m',cfg['model'],
          '-c','model_provider="trial"','-c','model_providers.trial='+inline,
          '-c','shell_environment_policy.inherit="none"','-c','model_reasoning_effort='+json.dumps(effort),
          '-o',str(output/'answer.json'),'-']
    started=time.monotonic()
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,encoding='utf-8',errors='replace',env=os.environ.copy())
    timed_out=False
    try:
        stdout,stderr=proc.communicate(text,timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        proc.kill()
        stdout,stderr=proc.communicate()
    events,tool_count=safe_events(stdout,secret)
    answer=output/'answer.json'
    if answer.exists():
        answer.write_text(redacted(answer.read_text(encoding='utf-8'),secret),encoding='utf-8')
    present=answer.exists() and answer.stat().st_size>0
    report={'schema_version':1,'model':cfg['model'],'base_url':cfg['base_url'],'reasoning_effort':effort,
            'tool':'Codex CLI','prompt_sha256':hashlib.sha256(raw).hexdigest(),'exit_code':proc.returncode,
            'timed_out':timed_out,'seconds':round(time.monotonic()-started,1),'answer_present':present,
            'tool_events':tool_count,'events':events,'stderr_tail':redacted(stderr,secret)[-1600:]}
    if present: report['answer_sha256']=hashlib.sha256(answer.read_bytes()).hexdigest()
    (output/'run.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes',type=Path,required=True)
    parser.add_argument('--route',required=True)
    parser.add_argument('--prompt',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--effort',choices=['low','medium','high'],default='low')
    parser.add_argument('--timeout',type=int,default=480)
    parser.add_argument('--codex',default=shutil.which('codex.exe') or shutil.which('codex.cmd') or shutil.which('codex'))
    args=parser.parse_args()
    try:
        if not args.codex: raise ValueError('Install a supported Codex CLI first, or pass --codex')
        if not 30<=args.timeout<=900: raise ValueError('Timeout must be between 30 and 900 seconds')
        cfg=route_config(args.routes,args.route)
        report=run_trial(args.codex,cfg,args.prompt,args.output,args.effort,args.timeout)
        print(json.dumps({k:report[k] for k in ['model','exit_code','timed_out','seconds','answer_present','tool_events']}))
        return 0 if report['exit_code']==0 and report['answer_present'] and not report['timed_out'] else 1
    except (OSError,ValueError,KeyError) as exc:
        # Never dump config values or a full subprocess invocation.
        print(json.dumps({'error_type':type(exc).__name__,'error':'Invalid input or unavailable CLI/credential; no successful trial recorded'}))
        return 2


if __name__=='__main__': raise SystemExit(main())
