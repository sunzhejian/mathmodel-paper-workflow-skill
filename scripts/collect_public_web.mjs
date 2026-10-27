import https from'node:https';import{lookup}from'node:dns/promises';import{isIP}from'node:net';export function publicImageAddress(ip){const f=isIP(ip);if(f===4){const[a,b,c]=ip.split('.').map(Number);return !(a===0||a===10||a===127||a>=224||a===100&&b>=64&&b<=127||a===169&&b===254||a===172&&b>=16&&b<=31||a===192&&(b===168||b===0&&c<=2)||a===198&&(b===18||b===19||b===51&&c===100)||a===203&&b===0&&c===113)}if(f!==6)return false;return /^[23][0-9a-f]{3}:/i.test(ip)&&!/^200[12]:/i.test(ip);}
import{createHash}from'node:crypto';const sha=b=>createHash('sha256').update(b).digest('hex');
const fail=(m,status=400)=>{throw Object.assign(Error(m),{status});},ua='ThevraResearchBot/1.0';
export function publicDataURL(raw){const u=new URL(raw);if(u.protocol!=='https:'||u.username||u.password||u.port&&u.port!=='443'||[...u.searchParams.keys()].some(k=>/token|password|secret|api.?key|signature|credential/i.test(k)))fail('采集仅接受不含登录凭据的公开HTTPS地址');const h=u.hostname.replace(/^\[|\]$/g,'');if(h==='localhost'||h.endsWith('.localhost')||isIP(h)&&!publicImageAddress(h))fail('不采集本机、内网或保留地址');u.hash='';return u;}
export async function publicDataRequest(raw,{signal,resolve=lookup}={}){const u=publicDataURL(raw),host=u.hostname.replace(/^\[|\]$/g,''),addresses=isIP(host)?[{address:host,family:isIP(host)}]:await resolve(host,{all:true,verbatim:true});if(!addresses.length||addresses.some(a=>!publicImageAddress(a.address)))fail('来源DNS解析到非公开地址');const chosen=addresses[0];signal?.throwIfAborted();return new Promise((resolve,reject)=>{const req=https.request(u,{method:'GET',signal,headers:{'user-agent':ua,accept:'text/html,application/json,text/plain,text/csv;q=0.9','accept-encoding':'identity'},lookup:(_host,options,done)=>options.all?done(null,[chosen]):done(null,chosen.address,chosen.family)},res=>{const chunks=[];let length=0;res.on('data',b=>{length+=b.length;if(length>2*1024*1024){res.destroy();reject(Error('来源单页超过2MiB，本页未纳入'));}else chunks.push(b);});res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,bytes:Buffer.concat(chunks),url:u.href}));});req.setTimeout(20000,()=>req.destroy(Error('网络数据请求超时，未自动重试')));req.on('error',reject);req.end();});}
const regex=s=>s.replace(/[.+?^{}()|[\]\\]/g,'\\$&').replaceAll('*','.*');
export function robotsPolicy(text,path){const groups=[];let agents=[],rules=[],delay=null,hadRules=false;const push=()=>{if(agents.length)groups.push({agents,rules,delay});agents=[];rules=[];delay=null;hadRules=false;};for(const raw of text.split(/\r?\n/)){const line=raw.split('#')[0].trim(),i=line.indexOf(':');if(i<0)continue;const key=line.slice(0,i).trim().toLowerCase(),value=line.slice(i+1).trim();if(key==='user-agent'){if(hadRules)push();agents.push(value.toLowerCase());}else if(['allow','disallow'].includes(key)&&agents.length){hadRules=true;if(value)rules.push({allow:key==='allow',path:value});}else if(key==='crawl-delay'&&agents.length){hadRules=true;const n=Number(value);if(Number.isFinite(n)&&n>=0)delay=n;}}push();let matching=groups.filter(g=>g.agents.some(a=>a!=='*'&&ua.toLowerCase().includes(a)));if(!matching.length)matching=groups.filter(g=>g.agents.includes('*'));const selected=matching.flatMap(g=>g.rules).filter(r=>new RegExp('^'+regex(r.path).replace(/\$$/,'$')).test(path)).sort((a,b)=>b.path.replaceAll('*','').length-a.path.replaceAll('*','').length||Number(b.allow)-Number(a.allow));return{allowed:selected[0]?.allow??true,crawl_delay:Math.max(1,...matching.map(g=>g.delay??1))};}
function decode(s){return String(s).replace(/&(?:amp|lt|gt|quot|apos|nbsp);|&#(?:x[0-9a-f]+|\d+);/gi,m=>{if(m.startsWith('&#')){const n=m[2].toLowerCase()==='x'?parseInt(m.slice(3),16):parseInt(m.slice(2),10);return n>0&&n<=0x10ffff?String.fromCodePoint(n):'';}return({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&apos;':"'",'&nbsp;':' '})[m.toLowerCase()]??m;});}
export function staticWebText(html){return decode(html.replace(/<(script|style|noscript)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]*>/g,' ')).replace(/\s+/g,' ').trim();}
const pointer=(obj,path)=>{if(!path)return obj;if(!path.startsWith('/'))fail('JSON路径使用JSON Pointer，如/data/comments');return path.slice(1).split('/').reduce((v,k)=>v?.[k.replaceAll('~1','/').replaceAll('~0','~')],obj);};
export async function crawlPublicData(input,{signal,request=publicDataRequest,wait=ms=>new Promise(r=>setTimeout(r,ms))}={}){
 if(!Array.isArray(input.urls)||!input.urls.length||input.urls.length>20)fail('每批提供1到20个起始网址');
 const max=input.max_pages??5;if(!Number.isInteger(max)||max<1||max>20)fail('每批采集1到20页，可按next_urls接续');
 for(const k of ['records_pointer','text_pointer','next_url_pointer'])if(input[k]!==undefined&&(typeof input[k]!=='string'||input[k].length>300||input[k]&&!input[k].startsWith('/')))fail('JSON字段使用最多300字的JSON Pointer');
 for(const k of ['follow_links','follow_next'])if(input[k]!==undefined&&typeof input[k]!=='boolean')fail('分页与链接开关须为布尔值');
 const queue=[...new Set(input.urls.map(x=>publicDataURL(x).href))],origins=new Set(queue.map(x=>new URL(x).origin)),seen=new Set(),pages=[],records=[],errors=[],robots=new Map(),last=new Map(),rawFiles={},pagination_issues=[],skipped_urls=[];
 const followNext=input.follow_next??!!input.next_url_pointer;let total=0,attempted=0,omitted_links=0,stop_reason='scope_processed';
 const responseError=(message,response)=>{const e=Object.assign(Error(message),{status:response.status,retryable:response.status===429||response.status>=500});if(e.retryable){const raw=String(response.headers?.['retry-after']??''),seconds=/^\d+$/.test(raw)?Number(raw):null,time=seconds===null?Date.parse(raw):Date.now()+seconds*1000;e.retry_after=new Date(Number.isFinite(time)?Math.max(Date.now(),time):Date.now()+60000).toISOString();}throw e;};
 async function rules(u){
  if(robots.has(u.origin))return robots.get(u.origin);const r=await request(u.origin+'/robots.txt',{signal});
  if([401,403,429].includes(r.status)||r.status>=500)responseError('robots.txt暂不可用或拒绝自动访问，停止该站点',r);
  if(![200,404,410].includes(r.status))fail('robots.txt状态未确认');const text=r.status===200?r.bytes.toString('utf8'):'';
  if(r.status===200&&/^\s*</.test(text))fail('robots.txt返回非规则页面，未继续采集');robots.set(u.origin,{text,status:r.status});return robots.get(u.origin);
 }
 function enqueue(raw,base,selected=false){
  try{const next=publicDataURL(new URL(raw,base).href);if(!origins.has(next.origin)){if(selected)pagination_issues.push({url:base,reason:'下一页网址超出本批起始网址的来源域，未自动跳转'});return;}
   if(seen.has(next.href)||queue.includes(next.href))return;if(queue.length>=200){omitted_links++;return;}queue.push(next.href);
  }catch(e){if(selected)pagination_issues.push({url:base,reason:'下一页网址无效：'+e.message});}
 }
 crawl:while(queue.length&&attempted<max){
  signal?.throwIfAborted();let url=queue.shift();if(seen.has(url))continue;seen.add(url);attempted++;
  const requested_url=url,recordStart=records.length,rawKey='page-'+String(pages.length+1).padStart(3,'0')+'.txt';
  try{
   let response;
   for(let hop=0;hop<4;hop++){
    const u=publicDataURL(url),robot=await rules(u),policy=robotsPolicy(robot.text,u.pathname+u.search);if(!policy.allowed)fail('robots.txt禁止采集此路径');if(policy.crawl_delay>60)fail('站点要求的自动访问间隔超过本批执行窗口');
    const pause=policy.crawl_delay*1000-(Date.now()-(last.get(u.origin)??0));if(pause>0)await wait(pause);signal?.throwIfAborted();last.set(u.origin,Date.now());response=await request(url,{signal});
    if(response.status>=300&&response.status<400){if(hop===3||!response.headers.location)fail('来源重定向未能在本批确认');url=publicDataURL(new URL(response.headers.location,url).href).href;if(seen.has(url)){skipped_urls.push({url:requested_url,resolved_url:url,reason:'duplicate_redirect_target'});continue crawl;}continue;}break;
   }
   if(response.status!==200)responseError('来源返回HTTP '+response.status+'，未自动重试',response);
   const encoding=response.headers['content-encoding'];if(encoding&&encoding!=='identity')fail('来源未返回登记的未压缩文本格式');const type=String(response.headers['content-type']??'');if(!/(html|json|text\/plain|text\/csv)/i.test(type))fail('仅采集公开HTML、JSON、CSV或纯文本');
   total+=response.bytes.length;if(total>8*1024*1024){queue.unshift(url);stop_reason='batch_byte_limit';break;}
   const declared=type.match(/charset\s*=\s*["']?([^;\s"']+)/i)?.[1]??response.bytes.toString('ascii',0,4096).match(/charset\s*=\s*["']?([a-z0-9_-]+)/i)?.[1]??'utf-8';let text;
   try{text=new TextDecoder(declared).decode(response.bytes);}catch{fail('来源字符编码不受支持：'+declared);}
   const raw_sha256=sha(response.bytes),id='web-'+sha(Buffer.from(url)).slice(0,24)+'-'+raw_sha256.slice(0,16),collected_at=new Date().toISOString(),page={id,url,requested_url,collected_at,content_type:type,raw_file:rawKey,raw_sha256,raw_bytes:response.bytes.length,charset:declared,decoding_replacements:(text.match(/\uFFFD/g)??[]).length,robots:{status:robots.get(new URL(url).origin)?.status,checked:true}};
   rawFiles[rawKey]=response.bytes;
   let jsonNext;
   if(/json/i.test(type)){
    const parsed=JSON.parse(text),items=pointer(parsed,input.records_pointer??'');if(!Array.isArray(items))fail('JSON结果不是记录数组，请指定records_pointer');const occurrences=new Map();
    for(const[i,item]of items.entries()){
     const value=pointer(item,input.text_pointer??'');if(typeof value!=='string')continue;if(records.length>=10000)fail('本批记录超过10000条，请按分页网址分批采集');
     const recordHash=sha(Buffer.from(JSON.stringify(item))),ordinal=occurrences.get(recordHash)??0;occurrences.set(recordHash,ordinal+1);
     records.push({id:'web-'+sha(Buffer.from(url)).slice(0,24)+'-'+recordHash.slice(0,24)+'-'+ordinal,text:value.slice(0,16000),text_truncated:value.length>16000,source:'web_public',source_url:url,collected_at,unit:'record',source_index:i,source_record_sha256:recordHash,source_page_sha256:raw_sha256});
    }
    if(followNext&&input.next_url_pointer)jsonNext=pointer(parsed,input.next_url_pointer);
   }else{
    const clean=/html/i.test(type)?staticWebText(text):text;records.push({id,text:clean.slice(0,16000),text_truncated:clean.length>16000,source:'web_public',source_url:url,collected_at,unit:'page',source_page_sha256:raw_sha256});
    if(input.follow_links&&/html/i.test(type))for(const m of text.matchAll(/<a\b[^>]*href\s*=\s*["']([^"']+)["']/gi))enqueue(decode(m[1]),url);
   }
   pages.push(page);seen.add(url);
   if(followNext){
    if(jsonNext!==undefined&&jsonNext!==null&&jsonNext!==''){if(typeof jsonNext==='string')enqueue(jsonNext,url,true);else pagination_issues.push({url,reason:'next_url_pointer未指向网址字符串，不将游标或对象猜成下一页'});}
    for(const m of String(response.headers.link??'').matchAll(/<([^>]+)>([^<]*)/g)){const rel=m[2].match(/;\s*rel\s*=\s*(?:"([^"]*)"|([^;,\s]+))/i);if((rel?.[1]??rel?.[2]??'').split(/\s+/).includes('next'))enqueue(m[1],url,true);}
   }
  }catch(e){
   if(signal?.aborted||e.name==='AbortError')throw e;records.splice(recordStart);delete rawFiles[rawKey];errors.push({url:requested_url,resolved_url:url,reason:e.message,status:e.status??null,retryable:e.retryable??(!e.status&&!(e instanceof SyntaxError)),retry_after:e.retry_after??null});
  }
 }
 const next_urls=[...new Set(queue)],retry_urls=errors.filter(e=>e.retryable).map(e=>({url:e.url,not_before:e.retry_after}));if(stop_reason==='scope_processed')stop_reason=next_urls.length?'batch_page_limit':errors.length?'source_errors':pagination_issues.length||omitted_links?'pagination_incomplete':'scope_processed';
 return{schema_version:2,attempted,pages,records,errors,next_urls,retry_urls,pagination_issues,skipped_urls,completion:{requested_scope_complete:!next_urls.length&&!errors.length&&!pagination_issues.length&&!omitted_links,stop_reason,pending:next_urls.length,failed:errors.length,omitted_links,site_exhaustiveness_verified:false},source:'web_public',collection_method:'公开HTTPS静态响应；遵守robots；未登录、不执行页面脚本。状态只对应指定网址和发现的分页，不代表整站全量或真人受访者',raw_files:rawFiles};
}

import{readFile,writeFile,mkdir}from'node:fs/promises';import path from'node:path';import{pathToFileURL}from'node:url';
export async function collectPublicMain(argv){if(argv.length!==2)throw Error('Usage: node collect_public_web.mjs config.json new-output-folder');const bytes=await readFile(argv[0]),config=JSON.parse(bytes.toString('utf8')),out=path.resolve(argv[1]);await mkdir(out,{recursive:false});const result=await crawlPublicData(config),files=[];async function save(name,b){await writeFile(path.join(out,name),b,{flag:'wx'});files.push({name,sha256:sha(b),bytes:Buffer.byteLength(b)});}for(const[name,data]of Object.entries(result.raw_files))await save('raw-'+name,data);delete result.raw_files;await save('texts.json',Buffer.from(JSON.stringify({source:'web_public',records:result.records},null,2)+'\n'));await writeFile(path.join(out,'collection.json'),JSON.stringify({...result,records:undefined,request:config,artifact_files:files,config_sha256:sha(bytes)},null,2)+'\n',{flag:'wx'});return{pages:result.pages.length,records:result.records.length,errors:result.errors,next_urls:result.next_urls,retry_urls:result.retry_urls,completion:result.completion};}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)collectPublicMain(process.argv.slice(2)).then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error(e.message);process.exitCode=1;});
