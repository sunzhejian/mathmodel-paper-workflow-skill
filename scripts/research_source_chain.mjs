import{readFile}from'node:fs/promises';import path from'node:path';import{createHash}from'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex');
export async function verifyTextSourceChain(file,bytes){
 const input={path:path.resolve(file),sha256:sha(bytes)},inputs=[input],sources=new Map([[input.path,input.sha256]]),seen=new Set([input.path]);let data=JSON.parse(bytes.toString('utf8')),current=data,total=0,depth=0;
 const read=async(ref,message)=>{
  if(typeof ref?.path!=='string'||!ref.path||!/^[a-f0-9]{64}$/.test(ref.sha256??''))throw Error('Invalid research source reference');
  const full=path.resolve(ref.path),known=sources.get(full);if(known&&known!==ref.sha256)throw Error('Research source version conflict');if(!known&&inputs.length>=1000)throw Error('Research sources exceed 1000 files');
  const raw=await readFile(full);if(!known){total+=raw.length;if(total>64*1024*1024)throw Error('Research sources exceed 64MiB');}if(sha(raw)!==ref.sha256)throw Error(message);
  if(!known){sources.set(full,ref.sha256);inputs.push({path:full,sha256:ref.sha256});}return raw;
 };
 for(;;){
  const refs=current?.web_collection?.inputs;if(refs!==undefined){if(!Array.isArray(refs)||refs.length>1000)throw Error('Invalid web collection inputs');for(const ref of refs)await read(ref,'Web collection source changed');}
  const parent=current?.cleaning?.input;if(!parent)break;const full=typeof parent.path==='string'?path.resolve(parent.path):'';if(!full||seen.has(full)||++depth>=8)throw Error('Invalid cleaning provenance');seen.add(full);current=JSON.parse((await read(parent,'Cleaning source changed')).toString('utf8'));
 }
 return{data,inputs};
}
