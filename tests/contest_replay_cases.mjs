import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm,readdir,symlink} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {exportContestReplay,verifyContestReplay} from '../scripts/contest_replay_bundle.mjs';
const h=b=>createHash('sha256').update(b).digest('hex'),rec=(p,b)=>({path:p,bytes:Buffer.byteLength(b),sha256:h(b)});
async function setup(t){
 const root=await mkdtemp(path.join(os.tmpdir(),'thevra-replay-'));t.after(async()=>{assert(root.startsWith(os.tmpdir()+path.sep));await rm(root,{force:true,recursive:true})});
 const sources=new Map([['inputs/runtime-data.csv','id,value\n1,2\n'],['code/solve.py','print("review before running")']]);
 const originals=new Map([['inputs/data.csv',sources.get('inputs/runtime-data.csv')]]);
 const input={canonical_path:'inputs/data.csv',project_path:'inputs/runtime-data.csv',...rec('unused',originals.get('inputs/data.csv'))};delete input.path;
 const options={destination:path.join(root,'export'),inputs:[input],artifacts:[rec('code/solve.py',sources.get('code/solve.py'))],readProjectFile:async p=>sources.get(p),readCanonicalFile:async p=>originals.get(p),context:{trial_id:'fixture',execution_status:'completed'}};
 return{root,sources,originals,options};
}
test('host names are preserved once in inputs while canonical copies do not confuse input globs',async t=>{
 const f=await setup(t),r=await exportContestReplay(f.options);assert.deepEqual(await readdir(r.path+'/inputs'),['runtime-data.csv']);
 assert.equal(await readFile(r.path+'/originals/data.csv','utf8'),f.originals.get('inputs/data.csv'));
 assert((await verifyContestReplay(r.path,r.manifest_sha256)).consistent);assert.equal(r.code_executed,false);
});
test('formal result, full result, paper, figure and support files are exported, without fixed three-folder loss',async t=>{
 const f=await setup(t);for(const p of ['paper/main.pdf','result/result1.xlsx','results_full/q.csv','figures/source.drawio','support/support.zip']){f.sources.set(p,'fixture '+p);f.options.artifacts.push(rec(p,f.sources.get(p)))}
 const r=await exportContestReplay(f.options);assert((await verifyContestReplay(r.path,r.manifest_sha256)).consistent);for(const a of f.options.artifacts)assert.equal(await readFile(r.path+'/'+a.path,'utf8'),f.sources.get(a.path));
});
test('changed source, canonical mismatch, unknown roots and credentials metadata are rejected before writing export',async t=>{
 for(const change of [
 f=>f.sources.set('inputs/runtime-data.csv','changed'),
 f=>f.originals.set('inputs/data.csv','other'),
 f=>f.options.artifacts.push(rec('credentials/token','secret')),
 f=>f.options.context.api_key='forbidden'
 ]){const f=await setup(t);change(f);await assert.rejects(()=>exportContestReplay(f.options));await assert.rejects(()=>readdir(f.options.destination),{code:'ENOENT'})}
});
test('case collisions, reserved paths, file-directory collisions and oversized plans fail closed',async t=>{
 for(const p of ['code/SOLVE.py','code/solve.py/child','../escape.py','code/CON.txt','code/hidden.','code/a\\b']){
  const f=await setup(t);f.options.artifacts.push(rec(p,'x'));f.sources.set(p,'x');await assert.rejects(()=>exportContestReplay(f.options));await assert.rejects(()=>readdir(f.options.destination),{code:'ENOENT'})
 }
 const f=await setup(t);await assert.rejects(()=>exportContestReplay({...f.options,maxBytes:1}),/byte bound/);
});
test('manifest fingerprint, deleted or changed inputs and unexpected files cannot pass replay verification',async t=>{
 const f=await setup(t),r=await exportContestReplay(f.options);await assert.rejects(()=>verifyContestReplay(r.path,'0'.repeat(64)),/manifest changed/);
 await writeFile(r.path+'/inputs/runtime-data.csv','modified');let v=await verifyContestReplay(r.path,r.manifest_sha256);assert(!v.consistent);assert(v.files.some(x=>x.state==='changed'));
 await rm(r.path+'/inputs/runtime-data.csv');await writeFile(r.path+'/extra.txt','extra');v=await verifyContestReplay(r.path,r.manifest_sha256);assert(!v.consistent);assert(v.files.some(x=>x.state==='missing'));assert.deepEqual(v.unexpected,['extra.txt']);
});
test('links are rejected rather than used as a purported portable original',async t=>{
 const f=await setup(t),r=await exportContestReplay(f.options);await mkdir(f.root+'/outside');await writeFile(f.root+'/outside/a','x');await symlink(f.root+'/outside',r.path+'/linked','junction');await assert.rejects(()=>verifyContestReplay(r.path,r.manifest_sha256),/linked/);
});
