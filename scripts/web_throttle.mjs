import {setTimeout as delay} from 'node:timers/promises';

export function abortableResult(promise,signal){
 const pending=Promise.resolve(promise);if(!signal)return pending;
 if(signal.aborted){pending.catch(()=>{});return Promise.reject(signal.reason);}
 return new Promise((resolve,reject)=>{
  const abort=()=>{cleanup();reject(signal.reason);},cleanup=()=>signal.removeEventListener('abort',abort);
  signal.addEventListener('abort',abort,{once:true});
  pending.then(value=>{cleanup();resolve(value);},error=>{cleanup();reject(error);});
 });
}
export const abortableDelay=(ms,signal)=>delay(ms,undefined,{signal});

export function retryDeadline(value,now=Date.now(),fallbackMs=60000){
 const raw=String(value??'').trim();let target;
 if(/^\d+$/.test(raw))target=now+Number(raw)*1000;
 else if(/[A-Za-z]/.test(raw)&&/GMT$/i.test(raw))target=Date.parse(raw);
 if(!Number.isFinite(target))target=now+fallbackMs;
 return Math.min(8640000000000000,Math.max(now,target));
}

export function createWebRequestGate({now=Date.now,wait=abortableDelay,minIntervalMs=1000,maxOrigins=512,maxPending=64,policyTtlMs=300000,maxWaitMs=60000}={}){
 for(const[k,v]of Object.entries({minIntervalMs,maxOrigins,maxPending,policyTtlMs,maxWaitMs}))if(!Number.isFinite(v)||v<0||(['maxOrigins','maxPending'].includes(k)&&(!Number.isInteger(v)||v<1)))throw Error('来源调度参数无效：'+k);
 const origins=new Map();
 const effective=s=>Math.max(minIntervalMs,s.policyUntil>now()?s.policyMs:0);
 const deferred=(message,until=null,status=null,code='origin_deferred')=>Object.assign(Error(message),{code,deferred:true,retryable:true,retry_after:until===null?null:new Date(until).toISOString(),prior_origin_status:status});
 function stateFor(origin){
  let s=origins.get(origin);if(s)return s;
  if(origins.size>=maxOrigins){
   const removable=[...origins.entries()].filter(([,v])=>!v.pending&&v.blockedUntil<=now()&&(v.lastStarted===null||v.lastStarted+effective(v)<=now())).sort((a,b)=>a[1].usedAt-b[1].usedAt)[0];
   if(!removable)throw deferred('来源调度暂时繁忙，未发出请求',null,null,'origin_capacity');origins.delete(removable[0]);
  }
  s={tail:Promise.resolve(),pending:0,lastStarted:null,policyMs:0,policyUntil:0,blockedUntil:0,blockedStatus:null,usedAt:now()};origins.set(origin,s);return s;
 }
 function rememberPolicy(url,intervalMs){
  if(!Number.isFinite(intervalMs)||intervalMs<0)throw Error('网站访问间隔无效');const s=stateFor(new URL(url).origin);s.policyMs=intervalMs;s.policyUntil=now()+policyTtlMs;s.usedAt=now();
 }
 async function run(url,{signal,crawlDelayMs,onResponse}={},request){
  signal?.throwIfAborted();if(typeof request!=='function')throw Error('网络调度缺少实际请求');const origin=new URL(url).origin,s=stateFor(origin);if(crawlDelayMs!==undefined)rememberPolicy(url,crawlDelayMs);
  if(s.blockedUntil>now())throw deferred('该来源处于已记录的冷却期，未发出请求',s.blockedUntil,s.blockedStatus,'origin_cooldown');
  if(s.pending>=maxPending)throw deferred('该来源访问队列已满，未发出请求',null,null,'origin_queue_full');
  const queuedAt=now(),turn=s.tail;let release;const done=new Promise(resolve=>release=resolve);s.tail=turn.then(()=>done);s.pending++;s.usedAt=queuedAt;let startedAt=null;
  try{
   await abortableResult(turn,signal);signal?.throwIfAborted();
   for(;;){
    if(s.blockedUntil>now())throw deferred('该来源处于已记录的冷却期，未发出请求',s.blockedUntil,s.blockedStatus,'origin_cooldown');
    const pause=s.lastStarted===null?0:s.lastStarted+effective(s)-now();if(pause<=0)break;
    if(pause>maxWaitMs)throw deferred('网站要求的等待超过本批执行窗口，未发出请求',s.lastStarted+effective(s),null,'origin_wait_window');
    await wait(pause,signal);signal?.throwIfAborted();
   }
   startedAt=now();s.lastStarted=startedAt;const response=await request();
   if(response.status===429||response.status>=500){s.blockedUntil=Math.max(s.blockedUntil,retryDeadline(response.headers?.['retry-after'],now()));s.blockedStatus=response.status;}
   signal?.throwIfAborted();const timing={scope:'current_process_origin',origin,queued_at:new Date(queuedAt).toISOString(),started_at:new Date(startedAt).toISOString(),finished_at:new Date(now()).toISOString(),waited_ms:Math.max(0,startedAt-queuedAt),minimum_interval_ms:effective(s)};
   const result={...response,request_timing:timing};if(onResponse)await onResponse(result);return result;
  }finally{s.pending--;s.usedAt=now();release();}
 }
 return{run,rememberPolicy,snapshot:()=>({origins:origins.size,pending:[...origins.values()].reduce((n,s)=>n+s.pending,0),blocked_origins:[...origins.values()].filter(s=>s.blockedUntil>now()).length})};
}
export const sharedWebRequestGate=createWebRequestGate();
