import{verifyTextSourceChain}from'./research_source_chain.mjs';
import {createHash} from 'node:crypto';const sha=b=>createHash('sha256').update(b).digest('hex');

export function textCohort(record,dataset){
 const source=record.source??dataset?.source??'unknown',unit=record.unit??dataset?.unit??'record';
 if(typeof source!=='string'||!source.trim()||source.length>160||typeof unit!=='string'||!unit.trim()||unit.length>60)throw Error('文本来源与分析单位须为明确的短文本');
 return{source,unit};
}

export function prepareTextCorpus(dataset,options={}){
 const input=Array.isArray(dataset)?dataset:dataset?.records;
 if(!Array.isArray(input)||input.length>10000)throw Error('清洗输入须为最多10000条具有唯一id与text的记录');
 if(!options||typeof options!=='object'||Array.isArray(options)||Object.keys(options).some(k=>!['deduplicate_text','min_chars'].includes(k)))throw Error('文本清洗仅接受明确登记的选项');
 const deduplicate_text=options.deduplicate_text??false,min_chars=options.min_chars??1;
 if(typeof deduplicate_text!=='boolean'||!Number.isInteger(min_chars)||min_chars<1||min_chars>1000)throw Error('文本去重须为布尔值，最短长度为1至1000字符');
 const rules={unicode:'NFKC',whitespace:'collapse_and_trim',empty:'remove',deduplicate_text,min_chars,dedup_scope:'source+unit+source_url+normalized_text'},ids=new Set(),duplicates=new Map(),records=[],log=[],cohorts=new Map();
 for(const row of input){
  if(typeof row?.id!=='string'||!row.id||row.id.length>500||ids.has(row.id)||typeof row.text!=='string'||row.text.length>16000)throw Error('原文本须有唯一id与最多16000字的text，不自动修补重复ID');
  ids.add(row.id);const cohort=textCohort(row,dataset),key=JSON.stringify(cohort),group=cohorts.get(key)??{...cohort,input:0,retained:0,removed_empty:0,removed_short:0,removed_duplicate:0};group.input++;cohorts.set(key,group);
  const text=row.text.normalize('NFKC').replace(/\s+/gu,' ').trim(),digest=sha(Buffer.from(text)),identity=JSON.stringify([cohort.source,cohort.unit,row.source_url??null,digest]);
  let reason=null,duplicate_of=null;
  if(!text){reason='empty';group.removed_empty++;}
  else if(Array.from(text).length<min_chars){reason='short';group.removed_short++;}
  else if(deduplicate_text&&duplicates.has(identity)){reason='duplicate';duplicate_of=duplicates.get(identity);group.removed_duplicate++;}
  else{duplicates.set(identity,row.id);group.retained++;records.push({...row,...cohort,text,original_text_sha256:sha(Buffer.from(row.text)),normalized_text_sha256:digest});}
  log.push({id:row.id,...cohort,status:reason?'removed':'retained',reason,duplicate_of,original_text_sha256:sha(Buffer.from(row.text)),normalized_text_sha256:digest,text_changed:text!==row.text});
 }
 return{schema_version:1,method:'traceable-text-corpus-v1',source:dataset?.source??'preserved_per_record',rules,rules_sha256:sha(Buffer.from(JSON.stringify(rules))),input_count:input.length,retained_count:records.length,removed_count:input.length-records.length,cohorts:[...cohorts.values()],records,log,note:'保留原输入；默认只标准化空白和Unicode并移除空文本。相同文字可来自不同受访者，文本去重仅在明确选择后执行，且不跨来源、分析单位或来源网址合并。'};
}

export function summarizeSentiment(records){
 const labels=['positive','negative','neutral','mixed','uncertain','empty'],groups=new Map();
 for(const row of records){const cohort=textCohort(row,{}),key=JSON.stringify(cohort),g=groups.get(key)??{...cohort,total:0,counts:Object.fromEntries(labels.map(k=>[k,0])),needs_review:0,truncated:0};if(!labels.includes(row.label))throw Error('未知情感类别');g.total++;g.counts[row.label]++;g.needs_review+=Number(row.needs_review===true);g.truncated+=Number(row.text_truncated===true);groups.set(key,g);}
 return [...groups.values()].map(g=>({...g,nonempty:g.total-g.counts.empty,classified:g.total-g.counts.empty-g.counts.uncertain,proportions_all:Object.fromEntries(labels.map(k=>[k,g.total?g.counts[k]/g.total:null])),proportion_denominator:'all_records_in_this_source_and_unit'}));
}

import{readFile,writeFile,mkdir}from'node:fs/promises';import path from'node:path';import{pathToFileURL}from'node:url';
export async function corpusMain(argv){if(argv.length<2||argv.length>3)throw Error('Usage: node prepare_text_corpus.mjs input.json new-output-folder [options.json]');const bytes=await readFile(argv[0]),options=argv[2]?JSON.parse(await readFile(argv[2],'utf8')):{},chain=await verifyTextSourceChain(argv[0],bytes),data=chain.data;const result=prepareTextCorpus(data,options),out=path.resolve(argv[1]);await mkdir(out,{recursive:false});const input={path:path.resolve(argv[0]),sha256:sha(bytes)};await writeFile(path.join(out,'texts.json'),JSON.stringify({source:result.source,records:result.records,cleaning:{input,rules:result.rules,rules_sha256:result.rules_sha256}},null,2)+'\n',{flag:'wx'});await writeFile(path.join(out,'cleaning.json'),JSON.stringify({...result,records:undefined,input},null,2)+'\n',{flag:'wx'});return{input:result.input_count,retained:result.retained_count,removed:result.removed_count};}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)corpusMain(process.argv.slice(2)).then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error(e.message);process.exitCode=1;});
