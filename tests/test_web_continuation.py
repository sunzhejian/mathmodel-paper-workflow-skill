import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for web continuation checks")
class WebContinuationTests(unittest.TestCase):
    def run_case(self, body):
        setup = """import assert from'node:assert/strict';import{readFile,writeFile,appendFile,mkdir,stat}from'node:fs/promises';import path from'node:path';import{createHash}from'node:crypto';
import{collectPublicMain,crawlPublicData}from'./scripts/collect_public_web.mjs';import{continuePublicMain}from'./scripts/continue_public_web.mjs';import{corpusMain}from'./scripts/prepare_text_corpus.mjs';
const dir=process.argv[1],sha=b=>createHash('sha256').update(b).digest('hex'),calls=[];
const transport=handler=>async(input)=>crawlPublicData(input,{wait:async()=>{},request:async url=>{calls.push(url);return url.endsWith('/robots.txt')?{status:404,headers:{},bytes:Buffer.alloc(0)}:handler(url);}});
const json=data=>({status:200,headers:{'content-type':'application/json'},bytes:Buffer.from(JSON.stringify(data))});
"""
        with tempfile.TemporaryDirectory(prefix="mathmodel-web-continuation-") as out:
            p = subprocess.run(["node", "--input-type=module", "-e", setup + body, out],
                               cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)

    def test_pending_inherits_fields_and_preserves_parent_and_unattempted_pages(self):
        result = self.run_case("""
const config=dir+'/request.json',folder=dir+'/first';await writeFile(config,JSON.stringify({urls:['https://example.test/one'],max_pages:1,records_pointer:'/items',text_pointer:'/body',next_url_pointer:'/next'}));
const crawl=transport(url=>json({items:[{body:url.endsWith('/one')?'原文':'续采'}],next:url.endsWith('/one')?'/two':'/three'}));
await collectPublicMain([config,folder],{crawl});const file=folder+'/collection.json',old=await readFile(file),hash=sha(old),preview=await continuePublicMain([file,hash,'--preview']);
assert.equal(preview.actions.pending.ready,true);const saved=await continuePublicMain([file,hash,dir+'/second'],{crawl});assert.equal(saved.records,1);assert.deepEqual(saved.next_urls,['https://example.test/three']);assert.deepEqual(await readFile(file),old);
const manifest=JSON.parse(await readFile(saved.manifest_path,'utf8'));assert.equal(manifest.request.text_pointer,'/body');assert.equal(manifest.continuation.parent.path,path.resolve(file));assert.equal(calls.filter(u=>u.endsWith('/one')).length,1);
await corpusMain([dir+'/second/texts.json',dir+'/clean']);const raw=folder+'/raw-page-001.txt';await appendFile(raw,'changed');const count=calls.length;await assert.rejects(continuePublicMain([saved.manifest_path,saved.manifest_sha256,dir+'/third'],{crawl}),/source changed/);assert.equal(calls.length,count);
console.log(JSON.stringify({inherited:true,parent_unchanged:true,tampered_parent_blocks_network:true}));
""")
        self.assertTrue(result["tampered_parent_blocks_network"])

    def test_csv_repair_uses_actual_columns_and_creates_new_version(self):
        result = self.run_case("""
const config=dir+'/request.json',folder=dir+'/first',raw='id,评价\\n1,"好用,方便"\\n2,不好用\\n3,';
await writeFile(config,JSON.stringify({urls:['https://example.test/a.csv'],csv_text_column:'wrong'}));const crawl=transport(()=>({status:200,headers:{'content-type':'text/csv; charset=utf-8'},bytes:Buffer.from(raw)}));
await collectPublicMain([config,folder],{crawl});const file=folder+'/collection.json',old=await readFile(file),hash=sha(old),preview=await continuePublicMain([file,hash,'--preview']);assert.equal(preview.actions.csv.ready,false);assert.deepEqual(preview.csv.sources[0].columns,['id','评价']);
const options=dir+'/options.json';await writeFile(options,JSON.stringify({intent:'csv',csv_text_column_index:1,csv_has_header:true,csv_delimiter:','}));const saved=await continuePublicMain([file,hash,dir+'/fixed',options],{crawl});assert.equal(saved.records,3);assert.equal(saved.completion.requested_scope_complete,true);assert.deepEqual(await readFile(file),old);
await assert.rejects(continuePublicMain([file,hash,dir+'/fixed',options],{crawl}),/exist/i);
const moved=await continuePublicMain([file,hash,dir+'/moved',options],{crawl:transport(()=>({status:200,headers:{'content-type':'text/csv; charset=utf-8'},bytes:Buffer.from('评价,id\\n好用,1')}))});assert.equal(moved.records,0);const changed=JSON.parse(await readFile(moved.manifest_path,'utf8'));assert.equal(changed.errors[0].header_changed,true);const again=await continuePublicMain([moved.manifest_path,moved.manifest_sha256,'--preview']);assert.equal(again.csv.selected_index,null);
console.log(JSON.stringify({csv_fixed:true,kept_empty:true,new_directory_only:true,moved_header_not_used:true}));
""")
        self.assertTrue(result["kept_empty"])

    def test_cooldown_and_unsafe_artifact_names_stop_before_requests(self):
        result = self.run_case("""
const config=dir+'/request.json',folder=dir+'/first';await writeFile(config,JSON.stringify({urls:['https://example.test/rate']}));const crawl=transport(()=>({status:429,headers:{'retry-after':'120'},bytes:Buffer.alloc(0)}));await collectPublicMain([config,folder],{crawl});
const file=folder+'/collection.json',raw=await readFile(file),options=dir+'/retry.json';await writeFile(options,JSON.stringify({intent:'retry'}));const preview=await continuePublicMain([file,sha(raw),'--preview',options]);assert.equal(preview.actions.retry.ready,false);const count=calls.length;await assert.rejects(continuePublicMain([file,sha(raw),dir+'/retry',options],{crawl}),/eligible/);assert.equal(calls.length,count);await assert.rejects(stat(dir+'/retry'));
const bad=JSON.parse(raw);bad.artifact_files[0].name='../texts.json';await writeFile(file,JSON.stringify(bad));const changed=await readFile(file);await assert.rejects(continuePublicMain([file,sha(changed),'--preview']),/filename/);assert.equal(calls.length,count);console.log(JSON.stringify({cooldown_no_requests:true,unsafe_path_rejected:true}));
""")
        self.assertTrue(result["unsafe_path_rejected"])


if __name__ == "__main__":
    unittest.main()
