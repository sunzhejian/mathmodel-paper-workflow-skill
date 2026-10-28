// Portable experiment export. Does not execute code or access model credentials.
import {mkdir,readFile,writeFile,readdir,lstat,realpath} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const hash=b=>createHash('sha256').update(b).digest('hex'),hex=/^[a-f0-9]{64}$/;
const roots=new Set(['code','results','result','results_full','figures','paper','reports','support']);
const forbidden=new Set(['node_modules','credentials','vendor']);
function safePath(s){
 if(typeof s!=='string'||!s||s.length>400||/[:\\\0]/.test(s)||s.split('/').some(p=>!p||p.startsWith('.')||/[. ]$/.test(p)||forbidden.has(p.toLowerCase())||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(p)))throw Error('Unsafe replay path');
 return s;
}
function descriptor(f){
 safePath(f.path);
 if(!Number.isSafeInteger(f.bytes)||f.bytes<0||!hex.test(f.sha256??''))throw Error('Expected saved bytes and SHA256');
 return f;
}
function claim(names,name){
 const folded=name.normalize('NFKC').toLowerCase();
 for(const previous of names)if(folded===previous||folded.startsWith(previous+'/')||previous.startsWith(folded+'/'))throw Error('Replay paths collide');
 names.add(folded);
}
async function regular(root,name){
 safePath(name);const base=await realpath(root);let current=base;
 for(const p of name.split('/')){current=path.join(current,p);const s=await lstat(current);if(s.isSymbolicLink()||!s.isFile()&&!s.isDirectory())throw Error('Replay links or special files are not allowed');}
 if(!(await lstat(current)).isFile()||!current.startsWith(base+path.sep))throw Error('Replay file required');
 return current;
}
function metadata(m){
 if(!m||Object.keys(m).some(k=>!['trial_id','runtime_version','requested_model','responded_model','execution_status','python_version'].includes(k))||Object.values(m).some(v=>v!==null&&(typeof v!=='string'||v.length>160)))throw Error('Only public replay metadata is allowed');
 return m;
}
export async function exportContestReplay({destination,inputs,artifacts,readProjectFile,readCanonicalFile,context={},maxBytes=256*1024*1024}){
 if(!Array.isArray(inputs)||!inputs.length||!Array.isArray(artifacts)||!artifacts.length||inputs.length+artifacts.length>5000)throw Error('Saved input mappings and published artifacts required');
 if(!Number.isSafeInteger(maxBytes)||maxBytes<=0||maxBytes>512*1024*1024)throw Error('Invalid export byte bound');
 metadata(context);
 const names=new Set(['replay-manifest.json']),sourceNames=new Set(),canonicalNames=new Set(),planned=[],mappings=[];
 for(const f of inputs){
  descriptor({path:f.project_path,bytes:f.bytes,sha256:f.sha256});safePath(f.canonical_path);
  if(!f.project_path.startsWith('inputs/')||!f.canonical_path.startsWith('inputs/'))throw Error('Original paths must be in inputs/');
  claim(sourceNames,f.project_path);claim(canonicalNames,f.canonical_path);
  // Preserve host aliases once under inputs/. Canonical copies stay outside the
  // runtime tree so glob-based solvers do not see the same dataset twice.
  const canonical='originals/'+f.canonical_path.slice(7);
  for(const name of [f.project_path,canonical])claim(names,name);
  planned.push({path:f.project_path,source_path:f.project_path,bytes:f.bytes,sha256:f.sha256,role:'runtime-original'});
  planned.push({path:canonical,source_path:f.canonical_path,bytes:f.bytes,sha256:f.sha256,role:'canonical-original'});
  mappings.push({canonical_path:canonical,project_path:f.project_path,bytes:f.bytes,sha256:f.sha256});
 }
 for(const item of artifacts){
  const f=descriptor(item);if(!roots.has(f.path.split('/')[0]))throw Error('Artifact outside published project roots');
  claim(names,f.path);planned.push({path:f.path,source_path:f.path,bytes:f.bytes,sha256:f.sha256,role:'artifact'});
 }
 const total=planned.reduce((n,f)=>n+f.bytes,0);if(total>maxBytes)throw Error('Replay exceeds declared byte bound');
 const snapshots=[];
 for(const f of planned){
  const bytes=Buffer.from(await(f.role==='canonical-original'?readCanonicalFile(f.source_path):readProjectFile(f.source_path)));
  if(bytes.length!==f.bytes||hash(bytes)!==f.sha256)throw Error('Saved source bytes changed: '+f.source_path);
  snapshots.push({record:f,bytes});
 }
 const target=path.resolve(destination),parent=path.dirname(target);
 if(await realpath(parent)!==parent||(await lstat(parent)).isSymbolicLink())throw Error('Replay parent must be a real directory');
 await mkdir(target);
 for(const {record:f,bytes} of snapshots){const dest=path.join(target,f.path);await mkdir(path.dirname(dest),{recursive:true});await writeFile(dest,bytes,{flag:'wx'});}
 const manifest={schema_version:1,context,mappings,files:planned.map(({source_path,...f})=>f),code_execution:'not-performed-by-export',scientific_verified:false};
 const bytes=Buffer.from(JSON.stringify(manifest,null,2)+'\n');await writeFile(path.join(target,'replay-manifest.json'),bytes,{flag:'wx'});
 return{path:target,manifest_sha256:hash(bytes),files:planned.length,total_bytes:total,code_executed:false};
}
export async function verifyContestReplay(root,expectedManifestSHA){
 if(!hex.test(expectedManifestSHA??''))throw Error('Expected manifest SHA256 required');
 if((await lstat(root)).isSymbolicLink())throw Error('Replay root cannot be linked');
 const bytes=await readFile(await regular(root,'replay-manifest.json'));
 if(hash(bytes)!==expectedManifestSHA)throw Error('Replay manifest changed');
 const m=JSON.parse(bytes);if(m.schema_version!==1||!Array.isArray(m.files)||m.files.length>10000||!Array.isArray(m.mappings))throw Error('Invalid replay manifest');
 metadata(m.context);const names=new Set(['replay-manifest.json']),checks=[];
 for(const f of m.files){descriptor(f);claim(names,f.path);if(!['runtime-original','canonical-original','artifact'].includes(f.role))throw Error('Invalid replay role');try{const b=await readFile(await regular(root,f.path));checks.push({path:f.path,state:b.length===f.bytes&&hash(b)===f.sha256?'match':'changed'});}catch(e){checks.push({path:f.path,state:e.code==='ENOENT'?'missing':'unavailable'});}}
 const expected=new Set(['replay-manifest.json',...m.files.map(f=>f.path)]),unexpected=[];
 async function walk(base,prefix=''){for(const e of await readdir(base,{withFileTypes:true})){const name=prefix+e.name;if(e.isSymbolicLink())throw Error('Replay contains linked files');if(e.isDirectory())await walk(path.join(base,e.name),name+'/');else if(!expected.has(name))unexpected.push(name);}}
 await walk(root);
 return{consistent:checks.every(f=>f.state==='match')&&unexpected.length===0,files:checks,unexpected,code_executed:false,scientific_verified:false};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
 const [command,root,expected]=process.argv.slice(2);
 if(command!=='verify')throw Error('Usage: node contest_replay_bundle.mjs verify replay-folder expected-manifest-sha256');
 const result=await verifyContestReplay(root,expected);console.log(JSON.stringify(result,null,2));if(!result.consistent)process.exitCode=1;
}
