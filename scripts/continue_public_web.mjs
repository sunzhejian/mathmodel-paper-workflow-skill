import{readFile,writeFile,mkdir,lstat}from'node:fs/promises';import path from'node:path';import{pathToFileURL}from'node:url';import{createHash}from'node:crypto';
import{crawlPublicData}from'./collect_public_web.mjs';import{collectionContinuation,continuationResult,publicContinuationPlan,continuationFields}from'./web_continuation_core.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const sourceName=s=>/^(?:collection\.json|texts\.json|raw-page-\d{3}\.txt)$/.test(path.basename(s));
export async function continuePublicMain(argv,{crawl=crawlPublicData}={}){
 if(argv.length<3||argv.length>4)throw Error('Usage: node continue_public_web.mjs collection.json expected-sha256 --preview|new-output-folder [options.json]');
 const [source,expected,destination,optionsFile]=argv,inputFile=path.resolve(source);if(path.basename(inputFile)!=='collection.json')throw Error('Select the saved collection.json');if(!/^[a-f0-9]{64}$/.test(expected))throw Error('Provide the SHA256 of the selected collection.json');
 const bytes=await readFile(inputFile);if(sha(bytes)!==expected)throw Error('Collection manifest changed');const saved=JSON.parse(bytes.toString('utf8')),options=optionsFile?JSON.parse(await readFile(optionsFile,'utf8')):{intent:'pending'};
 if(!options||Array.isArray(options)||Object.keys(options).some(k=>!['intent',...continuationFields].includes(k))||!['pending','retry','csv'].includes(options.intent??'pending'))throw Error('Invalid continuation options');
 if(!Array.isArray(saved.artifact_files)||saved.artifact_files.length>1000||saved.artifact_files.some(f=>typeof f?.name!=='string'||path.basename(f.name)!==f.name||/[\\/:]/.test(f.name)||!sourceName(f.name)))throw Error('Invalid collection artifact filename');
 if(saved.continuation?.source_inputs!==undefined&&(!Array.isArray(saved.continuation.source_inputs)||saved.continuation.source_inputs.length>1000))throw Error('Invalid inherited collection sources');
 const refs=new Map([[inputFile,expected]]);let total=0;
 for(const ref of[...(saved.artifact_files??[]).map(f=>({path:path.join(path.dirname(inputFile),f.name),sha256:f.sha256})),...(saved.continuation?.source_inputs??[])]){
  if(typeof ref?.path!=='string'||!sourceName(ref.path)||!/^[a-f0-9]{64}$/.test(ref.sha256??''))throw Error('Invalid collection source file');
  const full=path.resolve(ref.path);if(refs.has(full)){if(refs.get(full)!==ref.sha256)throw Error('Collection source version conflict');continue;}if(refs.size>=1000)throw Error('Collection source count exceeds 1000');
  if((await lstat(full)).isSymbolicLink())throw Error('Collection source links are not read');const raw=await readFile(full);total+=raw.length;if(total>64*1024*1024)throw Error('Collection sources exceed 64MiB');if(sha(raw)!==ref.sha256)throw Error('Collection source changed');refs.set(full,ref.sha256);
 }
 const inputs=[...refs].map(([path,sha256])=>({path,sha256})).sort((a,b)=>a.path.localeCompare(b.path)),sourceSet=sha(Buffer.from(JSON.stringify(inputs))),anchor={path:inputFile,sha256:expected},read=async ref=>{const bytes=await readFile(ref.path);return{bytes,sha256:sha(bytes)};},plan=await collectionContinuation(saved,anchor,sourceSet,inputs,options,{read,savedAt:saved.collected_at??null});
 if(destination==='--preview')return publicContinuationPlan(plan);
 const intent=options.intent??'pending',action=plan.actions[intent];if(!action.ready)throw Error(intent==='csv'?plan.csv?.reason??'CSV selection is not ready':'No eligible continuation URLs; inspect cooldown and review items with --preview');
 const out=path.resolve(destination);await mkdir(out,{recursive:false});let result=await crawl(action.request);result=continuationResult(result,plan,intent);result.continuation.source_inputs=inputs;
 for(const ref of inputs)if(sha(await readFile(ref.path))!==ref.sha256)throw Error('Collection source changed while collecting; result not saved');
 const files=[];async function save(name,data){await writeFile(path.join(out,name),data,{flag:'wx'});files.push({name,bytes:Buffer.byteLength(data),sha256:sha(data)});}
 for(const[name,data]of Object.entries(result.raw_files))await save('raw-'+name,data);delete result.raw_files;
 const rawInputs=files.map(f=>({path:path.join(out,f.name),sha256:f.sha256}));await save('texts.json',Buffer.from(JSON.stringify({source:'web_public',records:result.records,web_collection:{inputs:[...inputs,...rawInputs],complete:result.completion.requested_scope_complete}},null,2)+'\n'));
 const manifest=Buffer.from(JSON.stringify({...result,records:undefined,request:action.request,artifact_files:files},null,2)+'\n'),manifestPath=path.join(out,'collection.json');await writeFile(manifestPath,manifest,{flag:'wx'});
 return{manifest_path:manifestPath,manifest_sha256:sha(manifest),pages:result.pages.length,records:result.records.length,completion:result.completion,next_urls:result.next_urls,retry_urls:result.retry_urls,published:true,model_calls:0,source_scope:'explicit_manifest_and_checked_files'};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)continuePublicMain(process.argv.slice(2)).then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error(e.message);process.exitCode=1;});
