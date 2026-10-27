export function mergeWebRecords(batches){
 const records=[],seen=new Map(),duplicates=[],overlaps=new Map();let observed=0;
 for(const batch of batches){
  if(!Array.isArray(batch.records))throw Error('采集批次缺少实际文本记录');
  for(const row of batch.records){
   if(typeof row.id!=='string'||!row.id||typeof row.text!=='string'||row.text.length>16000||row.source!=='web_public'||!['page','record'].includes(row.unit)||typeof row.source_url!=='string')throw Error('采集记录的ID、原文、来源或分析单位不完整');
   observed++;const identity=JSON.stringify([row.text,row.source,row.unit,row.source_url,row.source_record_sha256??null]),prior=seen.get(row.id),observation={collection_path:batch.path,collected_at:row.collected_at??null,source_index:row.source_index??null,source_page_sha256:row.source_page_sha256??null};
   if(prior){if(prior.identity!==identity)throw Error('采集ID对应不同内容，不能静默合并；旧版编号冲突须按实际来源重建');prior.record.collection_observations.push(observation);duplicates.push({id:row.id,collection_path:batch.path,retained_collection:prior.path});continue;}
   if(records.length>=10000)throw Error('合并超过10000条，请按研究范围分组处理');const record={...row,collection_observations:[observation]};seen.set(row.id,{identity,record,path:batch.path});records.push(record);
   const key=JSON.stringify([row.unit,row.text.normalize('NFKC').replace(/\s+/g,' ').trim()]),list=overlaps.get(key)??[];list.push(row.id);overlaps.set(key,list);
  }
 }
 const observedURLs=new Set(batches.flatMap(b=>(b.pages??[]).flatMap(p=>[p.url,p.requested_url].filter(Boolean)))),unresolved=new Map();
 for(const batch of batches){for(const url of batch.next_urls??[])if(!observedURLs.has(url))unresolved.set(url,{url,kind:'pending'});for(const error of batch.errors??[])if(!observedURLs.has(error.url)&&!observedURLs.has(error.resolved_url))unresolved.set(error.url,{url:error.url,kind:'failed',retryable:error.retryable??false,not_before:error.retry_after??null});}
 const coverage={unresolved_urls:[...unresolved.values()],unresolved_pagination_issues:batches.flatMap(b=>b.pagination_issues??[]),omitted_links:batches.reduce((n,b)=>n+(b.completion?.omitted_links??0),0),batch_scope_status_known:batches.every(b=>!!b.completion),site_exhaustiveness_verified:false};
 return{schema_version:1,method:'collection-observation-merge-v1',batches:batches.map(b=>({path:b.path,records:b.records.length,completion:b.completion??null})),observed_records:observed,retained_records:records.length,repeated_observations:duplicates,possible_text_overlap:[...overlaps.values()].filter(ids=>ids.length>1).map(ids=>({ids,action:'retained_for_review_not_deleted'})),coverage,records,complete:coverage.batch_scope_status_known&&!coverage.unresolved_urls.length&&!coverage.unresolved_pagination_issues.length&&!coverage.omitted_links,note:'仅按同一ID且同内容的采集观察去除重复。相同措辞保留作复核，不能据此合并不同受访者，也不代表已完成整站或总体采集。'};
}
