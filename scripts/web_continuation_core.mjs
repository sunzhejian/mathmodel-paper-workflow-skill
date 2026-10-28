import{createHash}from'node:crypto';const sha=b=>createHash('sha256').update(b).digest('hex');
import{publicDataURL}from'./collect_public_web.mjs';
import{csvOptions,parseCSVText}from'./web_csv.mjs';
const fail=(message,status=400,code='research_continuation_invalid')=>{throw Object.assign(Error(message),{status,code});};
const list=v=>Array.isArray(v)?v:[],unique=v=>[...new Set(v)],intents=['pending','retry','csv'];
const requestKeys=['max_pages','follow_links','follow_next','records_pointer','text_pointer','next_url_pointer','csv_text_column','csv_text_column_index','csv_has_header','csv_delimiter'];
export const continuationFields=['csv_text_column_index','csv_has_header','csv_delimiter'];
export async function collectionContinuation(saved,anchor,sourceSet,inputs,input,{read,signal,now=Date.now(),savedAt=null,steps=0,original=anchor}={}){
 if(saved.source!=='web_public'||!saved.request||typeof saved.request!=='object')fail('历史记录缺少已保存的采集参数，请打开清单核对后新建采集');
 const options=Object.fromEntries(requestKeys.filter(k=>saved.request[k]!==undefined).map(k=>[k,saved.request[k]]));
 const canonical=u=>publicDataURL(u).href,pending=unique(list(saved.next_urls).map(canonical)),errors=list(saved.errors);if(pending.length>200||errors.length>200)fail('本批待处理记录过多，请分组核对');
 const holds=new Map();for(const e of errors){const time=Date.parse(e.retry_after??'');if(Number.isFinite(time)&&time>now){const origin=new URL(canonical(e.url)).origin;holds.set(origin,Math.max(holds.get(origin)??0,time));}}
 const held=u=>(holds.get(new URL(u).origin)??0)>now;
 const retry=unique(errors.filter(e=>e.retryable===true).map(e=>canonical(e.url))),csvErrors=errors.filter(e=>e.stage==='csv_extract'),csvUrls=unique(csvErrors.map(e=>canonical(e.url)));
 const csvView={sources:[],delimiter:input.csv_delimiter??options.csv_delimiter??',',has_header:input.csv_has_header??options.csv_has_header??true,selected_index:input.csv_text_column_index??options.csv_text_column_index??null,reason:null};
 if(input.csv_text_column_index===undefined&&csvErrors.some(e=>e.header_changed===true))csvView.selected_index=null;
 if(![',',';','\t'].includes(csvView.delimiter)||typeof csvView.has_header!=='boolean')fail('CSV表头或分隔符选项无效');
 if(csvView.selected_index!==null&&(!Number.isSafeInteger(csvView.selected_index)||csvView.selected_index<0||csvView.selected_index>255))fail('CSV文本列序号须从0开始');
 for(const error of csvErrors){
  signal?.throwIfAborted();const errorCollection=error.carried&&error.source_collection?.path?error.source_collection.path:anchor.path,rawPath=error.raw_file?errorCollection.slice(0,-'collection.json'.length)+'raw-'+error.raw_file:null,ref=rawPath&&inputs.find(f=>f.path===rawPath);
  const entry={url:canonical(error.url),raw_path:ref?.path??null,columns:[],reason:null};
  try{
   if(!ref)throw Error('历史记录未保存可核对的原始响应，请先打开清单核对');
   const file=await read(ref);if(file.sha256!==ref.sha256)fail('原始CSV已变化，请刷新接续选项',409);
   if(error.content_type&&!/\btext\/(?:csv|plain)\b/i.test(error.content_type))throw Error('来源返回的不是CSV或纯文本，请先核对来源页面');
   const decoded=new TextDecoder(error.charset??'utf-8',{fatal:true}).decode(file.bytes),parsed=parseCSVText(decoded,csvOptions({csv_text_column_index:0,csv_has_header:csvView.has_header,csv_delimiter:csvView.delimiter}));
   entry.columns=parsed.columns??Array.from({length:parsed.rows[0]?.length??0},(_,i)=>'第'+(i+1)+'列');entry.records=parsed.rows.length;entry.encoding=error.charset??'utf-8（字节校验通过，历史编码未登记）';
   if(csvView.selected_index===null&&options.csv_text_column&&csvView.has_header&&!csvErrors.some(e=>e.header_changed===true)){const indices=entry.columns.map((s,i)=>s===options.csv_text_column?i:-1).filter(i=>i>=0);if(indices.length===1)csvView.selected_index=indices[0];}
  }catch(e){if(signal?.aborted||e.name==='AbortError')throw e;entry.reason=e.status===409?e.message:'原始响应暂不能按这些选项提取：'+e.message;}
  csvView.sources.push(entry);
 }
 const csvValid=csvView.sources.length>0&&csvView.selected_index!==null&&csvView.sources.every(s=>!s.reason&&csvView.selected_index<s.columns.length);
 csvView.reason=csvErrors.length&&!csvValid?'请核对分隔符、表头并选择文本列；结构错误请先查看原始响应。':null;
 const actions={};for(const intent of intents){
  const candidates=intent==='pending'?pending:intent==='retry'?retry:csvUrls,ready=candidates.filter(u=>!held(u)),urls=ready.slice(0,20),request={...options,urls};
  if(intent==='csv'){delete request.csv_text_column;request.csv_text_column_index=csvView.selected_index;request.csv_has_header=csvView.has_header;request.csv_delimiter=csvView.delimiter;}
  const valid=urls.length>0&&(intent!=='csv'||csvValid),token=sha(Buffer.from(JSON.stringify({source:anchor,source_set:sourceSet,intent,request})));
  actions[intent]={intent,count:urls.length,total:candidates.length,waiting:candidates.filter(held).length,remaining:Math.max(0,candidates.length-urls.length),ready:valid,action_key:valid?token:null,request:valid?request:null};
 }
 const waiting=[...holds].map(([origin,time])=>({origin,not_before:new Date(time).toISOString()})),unhandled=errors.filter(e=>e.retryable!==true&&e.stage!=='csv_extract');
 const publicPlan={source:anchor,requested_source:original,forwarded:steps,ready:true,source_set_sha256:sourceSet,actions,csv:csvErrors.length?csvView:null,waiting,review_count:unhandled.length,pagination_issues:list(saved.pagination_issues),message:steps?'已沿用最新接续批次，已采内容保留。':'接续基于这份保存记录；每次最多20个起始网址，原成功页面保留。',saved_at:savedAt};
 return{...publicPlan,_saved:saved,_inputs:inputs};
}

export function publicContinuationPlan(plan){const{_saved,_inputs,...visible}=plan;return visible;}
export function continuationResult(result,plan,intent){
 if(intent==='csv'&&plan.csv?.has_header){
  const rejected=new Set(),kept=[];
  for(const page of result.pages){const previous=plan.csv.sources.find(s=>s.url===(page.requested_url??page.url)),index=plan.csv.selected_index,expected=previous?.columns?.[index],actual=page.extraction?.columns?.[index];
   if(expected!==undefined&&expected!==actual){rejected.add(page.url+':'+page.raw_sha256);result.errors.push({url:page.requested_url??page.url,resolved_url:page.url,reason:'重新采集的表头已变化，请重新核对文本列',status:null,retryable:false,retry_after:null,stage:'csv_extract',header_changed:true,raw_file:page.raw_file,raw_sha256:page.raw_sha256,raw_bytes:page.raw_bytes,charset:page.charset,content_type:page.content_type});}else kept.push(page);
  }
  result.pages=kept;result.records=result.records.filter(r=>!rejected.has(r.source_url+':'+r.source_page_sha256));
 }
 const action=plan.actions[intent],done=new Set(result.pages.flatMap(p=>[p.url,p.requested_url]).filter(Boolean)),processed=new Set([...done,...result.errors.map(e=>e.url),...list(result.skipped_urls).map(e=>e.url)]);
 const carried=list(plan._saved.errors).filter(e=>!processed.has(e.url)).map(e=>({...e,carried:true,status:null,recorded_status:e.carried?e.recorded_status:e.status,source_collection:e.source_collection??{...plan.source,saved_at:plan.saved_at}}));
 const seen=new Set(result.errors.map(e=>e.url));result.errors.push(...carried.filter(e=>!seen.has(e.url)));
 const carriedUrls=new Set(carried.map(e=>e.url));result.next_urls=unique([...result.next_urls,...list(plan._saved.next_urls).filter(u=>!processed.has(u))]).filter(u=>!carriedUrls.has(u));
 result.pagination_issues.push(...list(plan._saved.pagination_issues).filter(e=>!processed.has(e.url)));
 result.retry_urls=result.errors.filter(e=>e.retryable).map(e=>({url:e.url,not_before:e.retry_after??null}));
 result.completion={...result.completion,pending:result.next_urls.length,failed:result.errors.length,omitted_links:Math.max(result.completion.omitted_links??0,plan._saved.completion?.omitted_links??0)};
 result.completion.requested_scope_complete=!result.next_urls.length&&!result.errors.length&&!result.pagination_issues.length&&!result.completion.omitted_links;
 if(!result.completion.requested_scope_complete)result.completion.stop_reason='continuation_incomplete';
 result.continuation={parent:plan.source,root:plan._saved.continuation?.root??plan.source,requested_source:plan.requested_source,forwarded:plan.forwarded,intent,selected_urls:action.request.urls,carried_errors:carried.length,source_set_sha256:plan.source_set_sha256};
 return result;
}
