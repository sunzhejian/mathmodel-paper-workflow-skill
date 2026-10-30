import {createHash} from 'node:crypto';
const plain=value=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&[Object.prototype,null].includes(Object.getPrototypeOf(value));
function canonical(value,seen=new Set()) {if(value===null||typeof value==='string'||typeof value==='boolean'||typeof value==='number'&&Number.isFinite(value))return JSON.stringify(value);if(typeof value!=='object'||seen.has(value))throw Error('Input must be finite JSON without cycles');seen.add(value);let result;if(Array.isArray(value))result='['+value.map(x=>canonical(x,seen)).join(',')+']';else if(plain(value))result='{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k],seen)).join(',')+'}';else throw Error('Input must be plain JSON');seen.delete(value);return result;}
const surveyContentHash=value=>createHash('sha256').update(canonical(value)).digest('hex');

export const SURVEY_STOP_WORDS=Object.freeze('的 了 是 在 和 与 及 也 都 就 而 并 但 对 把 被 将 以 从 到 等 中 上 下 这 那 这个 那个 一些 一种 可以 可能 需要 认为 觉得 比较 非常 进行 通过 因此 因为 所以 以及 自己 我 我们 你 你们 他们 它 其 该 本 更 很 吗 呢 啊 the a an and or to of in for with this that is are it i we you'.split(' '));
export const SURVEY_PHRASES=Object.freeze('人工复核 核验负担 核验成本 来源追溯 来源提示 公开资料 个人材料 敏感材料 隐私信任 隐私保护 删除记录 删除期限 免费功能 基础功能 增强功能 第三方评估 安全评估 文本摘要 文字摘要 表格辅助 生成式AI 办公服务 支付意愿 付费意愿 付费 上传 复核 核验 隐私 准确性 免费'.split(' '));
const sourceLabels={ai:'AI受访者调研',pilot:'AI预调查试答',real:'真实回收（用户声明）'};
const fail=message=>{throw Object.assign(Error(message),{status:400});};
const xml=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const stableCompare=(a,b)=>a<b?-1:a>b?1:0;
function wordsInput(value,label,max){if(value===undefined)return[];if(!Array.isArray(value)||value.length>max||value.some(s=>typeof s!=='string'||!s.trim()||s.length>40))fail(label+'应为最多'+max+'个非空短词');return [...new Set(value.map(s=>s.normalize('NFKC').trim().toLowerCase()))].sort(stableCompare);}
const escapeRegex=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export function surveyWordcloudPolicyKey(){return surveyContentHash({algorithm:'intl-segmenter-zh-domain-phrases-v2',tokenizer_sha256:sha(tokenizer.toString()),icu:process.versions.icu,stop_words:SURVEY_STOP_WORDS,phrases:SURVEY_PHRASES});}
export function surveyWordcloudCohort(state,{dataset='ai',question_id}={}){
 if(!sourceLabels[dataset])fail('请选择AI调研、AI预调查或真实回收');
 const q=state.schema.questions.find(q=>q.id===(question_id??state.schema.questions.find(q=>q.type==='text')?.id));if(!q||q.type!=='text')fail('请选择当前问卷中的开放题');
 const revision=surveyContentHash(state.schema),rows=(dataset==='real'?state.realData:state.responses).filter(r=>r.surveyRevisionHash===revision&&r.source===(dataset==='real'?'human_reported':'ai_synthetic')&&(dataset==='real'||(state.responseMeta?.[r.id]?.purpose??'research')===(dataset==='pilot'?'pilot':'research'))).sort((a,b)=>stableCompare(a.id,b.id));
 if(new Set(rows.map(r=>r.id)).size!==rows.length)fail('答卷标识重复，请先核对导入批次，不自动删除原始记录');
 const values=rows.map(r=>({id:r.id,text:typeof r.answers?.[q.id]==='string'?r.answers[q.id]:null,skipped:(r.skippedQuestionIds??[]).includes(q.id)}));
 return{q,revision,rows,cohort_digest:surveyContentHash({contract:2,revision,dataset,question:q.id,records:values})};
}
const contactSafe=text=>text.replace(/https?:\/\/\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)/giu,'〔联系方式已隐去〕');
function tokenizer(phrases,stops){
 const segmenter=new Intl.Segmenter('zh-CN',{granularity:'word'}),known=new Set(phrases),pattern=phrases.length?new RegExp('('+[...phrases].sort((a,b)=>b.length-a.length||stableCompare(a,b)).map(escapeRegex).join('|')+')','gu'):null;
 return text=>{
  // Remove common contact identifiers before segmentation. This is not a general named-entity anonymizer.
  const cleaned=text.normalize('NFKC').toLowerCase().replace(/https?:\/\/\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)/giu,' ');
  const raw=[];
  for(const chunk of pattern?cleaned.split(pattern):[cleaned]){
   if(known.has(chunk)){raw.push(chunk);continue;}
   raw.push(...[...segmenter.segment(chunk)].map(x=>x.isWordLike?x.segment:null));
  }
  const tokens=[];
  for(let i=0;i<raw.length;i++){
   let word=raw[i];if(!word)continue;if(['不','未','没','无','非'].includes(word)&&raw[i+1])word+=raw[++i];
   if([...word].length<2||word.length>40||stops.has(word)||!/[\p{L}]/u.test(word)||/^\d+$/u.test(word))continue;
   tokens.push(word);
  }
  return tokens;
 };
}

export function buildSurveyWordcloud(state,{dataset='ai',question_id,stop_words,phrases,max_terms=40,layout='rectangle',palette='classic',density='balanced'}={}){
 if(!Number.isSafeInteger(max_terms)||max_terms<1||max_terms>80)fail('展示词数应为1到80');
 if(!['rectangle','ellipse','dialogue','columns'].includes(layout))fail('请选择矩形、椭圆、对话气泡或分栏版式');
 if(!['classic','teal','blue','mono'].includes(palette))fail('请选择可用的词云配色');
 if(!['balanced','airy','compact'].includes(density))fail('请选择适中、疏朗或紧凑的词云密度');
 const {q,revision,rows,cohort_digest}=surveyWordcloudCohort(state,{dataset,question_id});
 const extraStops=wordsInput(stop_words,'停用词',100),extraPhrases=wordsInput(phrases,'领域词',50),allStops=[...new Set([...SURVEY_STOP_WORDS,...extraStops])].sort(stableCompare),allPhrases=[...new Set([...SURVEY_PHRASES,...extraPhrases].map(s=>s.toLowerCase()))].sort(stableCompare),split=tokenizer(allPhrases,new Set(allStops));
 const counts=new Map(),sourceRows=[];let nonempty=0,totalTokens=0,totalChars=0;
 for(const row of rows){
  const raw=row.answers?.[q.id];if(typeof raw!=='string'||!raw.trim())continue;
  totalChars+=raw.length;if(totalChars>2000000)fail('开放文本超过本次可视化处理上限，请按批次导出分析');nonempty++;
  const tokens=split(raw);totalTokens+=tokens.length;sourceRows.push({id:row.id,text:raw});
  for(const word of tokens){const count=counts.get(word)??{word,occurrences:0,documents:0,record_ids:[]};count.occurrences++;counts.set(word,count);}
  for(const word of new Set(tokens)){const c=counts.get(word);c.documents++;c.record_ids.push(row.id);}
 }
 const terms=[...counts.values()].sort((a,b)=>b.documents-a.documents||b.occurrences-a.occurrences||stableCompare(a.word,b.word));
 const settings={algorithm:'intl-segmenter-zh-domain-phrases-v2',tokenizer_sha256:sha(tokenizer.toString()),icu:process.versions.icu,stop_words:allStops,phrases:allPhrases,minimum_characters:2,max_terms,weight:'documents',negation_prefixes:['不','未','没','无','非'],negation:'Chinese prefix joined to following adjacent token only; no crossing punctuation or whitespace; no sentiment inference'};
 const appearance=layout==='rectangle'&&palette==='classic'&&density==='balanced'?{}:{layout,palette,density};
 if(Object.keys(appearance).length)settings.appearance=appearance;
 const digest=surveyContentHash({contract:2,cohort_digest,settings}),sourceIndex=new Map(sourceRows.map((r,i)=>[r.id,{...r,anonymous_id:'T'+String(i+1).padStart(4,'0')}]));
 const contexts=terms.slice(0,max_terms).map(t=>({word:t.word,shown:Math.min(3,t.record_ids.length),total_documents:t.documents,samples:t.record_ids.slice(0,3).map(id=>{const r=sourceIndex.get(id);return{anonymous_id:r.anonymous_id,record_id:id,text:[...contactSafe(r.text)].slice(0,180).join(''),original_text_sha256:sha(r.text),excerpt:true};})}));
 return {schema_version:2,version:state.version??null,dataset,source_label:sourceLabels[dataset],question_id:q.id,question_text:q.text,survey_revision_hash:revision,cohort_digest,policy_key:surveyWordcloudPolicyKey(),input_digest:digest,requested_options:{dataset,question_id:q.id,max_terms,stop_words:extraStops,phrases:extraPhrases,...appearance},counts:{accepted_records:rows.length,nonempty_texts:nonempty,empty_or_skipped:rows.length-nonempty,token_occurrences:totalTokens,unique_terms:terms.length},settings,terms,shown_terms:terms.slice(0,max_terms),contexts,scope:'每条答卷对同词的文档频数最多计1；词出现次数另列。来源与问卷版本分开；未另作语义清洗、主题编码或情感推断。原文回查显示片段，常见联系方式已过滤，姓名和单位等仍需人工匿名核对。'};
}

export function surveyWordcloudLayout(result){
 const width=1120,height=680,boxes=[],{layout='rectangle',palette='classic',density='balanced'}=result.settings?.appearance??{};
 const colors={classic:['#225b6a','#4a7c59','#94623b','#516884','#665978'],teal:['#163c4c','#1f6972','#397f83','#656951','#426456'],blue:['#203d61','#345c85','#4c739a','#6b859c','#425362'],mono:['#18242c','#34434c','#4c5960','#657079','#26363f']}[palette];
 if(!colors||!['rectangle','ellipse','dialogue','columns'].includes(layout)||!['balanced','airy','compact'].includes(density))fail('词云展示设置不正确');
 const gap={airy:22,balanced:14,compact:8}[density],padding=gap/2;
 const inside=b=>{
  if(b.x<30||b.y<142||b.x+b.w>width-30||b.y+b.h>height-94)return false;
  if(layout==='ellipse')return [[b.x,b.y],[b.x+b.w,b.y],[b.x,b.y+b.h],[b.x+b.w,b.y+b.h]].every(([x,y])=>((x-560)/520)**2+((y-350)/202)**2<=1);
  if(layout==='dialogue'&&(b.x<58||b.x+b.w>1062||b.y<160||b.y+b.h>552))return false;
  if(layout==='columns'&&b.x<580&&b.x+b.w>540)return false;
  return true;
 };
 const max=result.shown_terms[0]?.documents??1;
 let previousSize=Infinity;
 for(const [index,t] of result.shown_terms.entries()){
  let size=Math.min(previousSize,16+42*Math.sqrt(t.documents/max)),box=null;
  for(let shrink=0;shrink<8&&!box;shrink++,size*=.88){
   const w=[...t.word].reduce((n,c)=>n+(/[\p{Script=Han}]/u.test(c)?1:.65),0)*size+gap,h=size*1.4+padding;
   for(let k=0;k<3800;k++){
    const a=k*.38,r=3.4*Math.sqrt(k),center=layout==='columns'?(index%2?820:300):width/2,x=center+Math.cos(a)*r*(layout==='columns'?1.1:2.45)-w/2,y=350+Math.sin(a)*r*1.32-h/2;
    const b={x,y,w,h,size};if(!inside(b)||boxes.some(p=>x<p.x+p.w&&x+w>p.x&&y<p.y+p.h&&y+h>p.y))continue;
    box={...b,...t,color:colors[index%colors.length]};break;
   }
  }
  if(box){boxes.push(box);previousSize=box.size;}
 }
 return{width,height,layout,palette,density,boxes};
}
export function surveyWordcloudSvg(result){
 const {width,height,layout,boxes}=surveyWordcloudLayout(result);
 const ornament=layout==='dialogue'?'<path d="M70 150 H1050 Q1075 150 1075 175 V530 Q1075 555 1050 555 H860 L820 580 L815 555 H70 Q45 555 45 530 V175 Q45 150 70 150 Z" fill="#f6f9fa" stroke="#dce5e9"/>':layout==='columns'?'<path d="M560 157 V556" stroke="#e1e7eb"/>':'';
 const text=boxes.map(b=>`<text x="${(b.x+b.w/2).toFixed(1)}" y="${(b.y+b.h/2).toFixed(1)}" text-anchor="middle" dominant-baseline="central" font-size="${b.size.toFixed(1)}" fill="${b.color}"><title>${xml(b.word)}：${b.documents}份答卷，出现${b.occurrences}次</title>${xml(b.word)}</text>`).join('');
 return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="开放回答词云"><metadata>${xml(JSON.stringify({input_digest:result.input_digest,appearance:result.settings?.appearance??{layout:'rectangle',palette:'classic',density:'balanced'}}))}</metadata><rect width="100%" height="100%" fill="#fff"/>${ornament}<g font-family="Microsoft YaHei,SimSun,Noto Sans CJK SC,sans-serif"><text x="40" y="48" font-size="27" fill="#20262e">${xml(result.question_id)} 开放回答词云</text><text x="40" y="82" font-size="18" fill="#5d6872">${xml(result.source_label)} · 非空文本 ${result.counts.nonempty_texts} 条 · 按包含词语的答卷数缩放</text>${text||'<text x="560" y="340" text-anchor="middle" font-size="24" fill="#666">当前没有可展示词语，请核对文本或停用词</text>'}<text x="40" y="616" font-size="16" fill="#5d6872">计数口径：每份答卷对同一词语计1次；全部出现次数见词频表</text><text x="40" y="646" font-size="15" fill="#6b747c">显示 ${boxes.length}/${result.terms.length} 个词 · 完整频次与规则请导出CSV/JSON</text></g></svg>`;
}

export function surveyWordcloudCsv(result){
 const cell=v=>'"'+String(typeof v==='string'&&/^[\s]*[=+@\-\t\r]/.test(v)?"'"+v:v).replaceAll('"','""')+'"';
 return '\uFEFF'+[['word','documents','occurrences','nonempty_texts','dataset','question_id','input_digest'],...result.terms.map(t=>[t.word,t.documents,t.occurrences,result.counts.nonempty_texts,result.dataset,result.question_id,result.input_digest])].map(r=>r.map(cell).join(',')).join('\r\n');
}


import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import path from 'node:path';import {pathToFileURL}from'node:url';

export async function wordcloudMain(argv){
 const args={};for(let i=0;i<argv.length;i+=2){if(!/^--(?:input|out|dataset|question|max-terms|stop-words|phrases|layout|palette|density)$/.test(argv[i])||!argv[i+1]||argv[i+1].startsWith('--'))throw Error('Usage: node survey_wordcloud.mjs --input records.json --out new-output-directory [--dataset ai|pilot|real] [--question Q15] [--stop-words words.txt] [--phrases phrases.txt]');args[argv[i].slice(2)]=argv[i+1];}
 if(!args.input||!args.out)throw Error('--input and --out are required');
 const input=path.resolve(args.input),out=path.resolve(args.out),info=await stat(input);if(info.size>16*1024*1024)throw Error('Input exceeds 16 MiB');const bytes=await readFile(input),value=JSON.parse(bytes.toString('utf8'));
 let state=value,dataset=args.dataset??value.dataset??value.source??'ai';
 if(!value.schema){
  if(!['ai','pilot','real'].includes(dataset)||!Array.isArray(value.records)||value.records.some(r=>typeof r.id!=='string'||!r.id||typeof r.text!=='string')||new Set(value.records.map(r=>r.id)).size!==value.records.length)throw Error('Normalized input requires dataset=ai|pilot|real and unique {id,text} records');
  if((value.dataset??value.source)&&dataset!==(value.dataset??value.source))throw Error('Dataset override must not relabel declared source');
  const question=args.question??value.question_id??'text',schema={id:'open-text-input',title:value.title??'开放文本',questions:[{id:question,type:'text',text:value.question_text??'开放文本'}]},revision=surveyContentHash(schema);
  const records=value.records.map(r=>({id:r.id,answers:{[question]:r.text},surveyRevisionHash:revision,source:dataset==='real'?'human_reported':'ai_synthetic'}));
  state={schema,responses:dataset==='real'?[]:records,realData:dataset==='real'?records:[],responseMeta:Object.fromEntries(records.map(r=>[r.id,{purpose:dataset==='pilot'?'pilot':'research'}]))};
 }
 const lines=async filename=>filename?(await readFile(path.resolve(filename),'utf8')).split(/\r?\n/).map(s=>s.trim()).filter(Boolean):undefined;
 const result=buildSurveyWordcloud(state,{dataset,question_id:args.question,max_terms:args['max-terms']?Number(args['max-terms']):40,stop_words:await lines(args['stop-words']),phrases:await lines(args.phrases),layout:args.layout,palette:args.palette,density:args.density});result.input_file_sha256=sha(bytes);
 const outputs={'wordcloud.svg':surveyWordcloudSvg(result),'word-frequency.csv':surveyWordcloudCsv(result),'wordcloud.json':JSON.stringify(result,null,2)+'\n'};
 await mkdir(out,{recursive:true});for(const name of Object.keys(outputs)){try{await stat(path.join(out,name));throw Error('Output exists; choose a new directory: '+name);}catch(e){if(e.code!=='ENOENT')throw e;}}
 for(const [name,content]of Object.entries(outputs))await writeFile(path.join(out,name),content);
 const manifest={input_file_sha256:result.input_file_sha256,input_digest:result.input_digest,source:result.source_label,nonempty_texts:result.counts.nonempty_texts,files:Object.entries(outputs).map(([name,content])=>({path:name,bytes:Buffer.byteLength(content),sha256:sha(content)})),model_calls:0};await writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');console.log(JSON.stringify(manifest));return manifest;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)wordcloudMain(process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1;});
