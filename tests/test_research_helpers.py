import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = os.environ.get('MATHMODEL_NODE') or shutil.which('node')


@unittest.skipUnless(NODE, 'Node.js optional research helpers')
class ResearchHelperTests(unittest.TestCase):
    def test_sentiment_cli_retains_source_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            source=base/'texts.json'
            source.write_text(json.dumps(dict(source='fixture_only', records=[dict(id='a', text='不好用', source='ai_synthetic'), dict(id='b', text='办公资料')]), ensure_ascii=False), encoding='utf-8')
            command=[NODE, str(ROOT/'scripts/text_sentiment_baseline.mjs'), str(source), str(base/'out')]
            completed=subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data=json.loads((base/'out/sentiment.json').read_text(encoding='utf-8'))
            self.assertEqual(data['records'][0]['label'], 'negative')
            self.assertEqual(data['records'][0]['source'], 'ai_synthetic')
            self.assertEqual(data['records'][1]['label'], 'uncertain')
            self.assertIsNone(data['accuracy'])
            self.assertEqual(data['input_file_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_public_crawler_robot_and_private_url_checks_work_without_network(self):
        code="const m=await import(process.argv[1]);let blocked=false;try{m.publicDataURL('https://127.0.0.1/')}catch{blocked=true}console.log(JSON.stringify({blocked,denied:!m.robotsPolicy('User-agent: *\\nDisallow: /private','/private/x').allowed}));"
        result=subprocess.run([NODE, '--input-type=module', '-e', code, (ROOT/'scripts/collect_public_web.mjs').as_uri()], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), dict(blocked=True, denied=True))

    def test_batch_merge_verifies_raw_files_and_keeps_equal_texts(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            items=[]
            for name in ['first','second']:
                batch=base/name
                batch.mkdir()
                raw=json.dumps(dict(id=name,text='满意')).encode('utf-8')
                texts=json.dumps(dict(source='web_public',records=[dict(id=name,text='满意',source='web_public',unit='record',source_url='https://example.test/'+name)]),ensure_ascii=False).encode('utf-8')
                (batch/'raw-page-001.txt').write_bytes(raw)
                (batch/'texts.json').write_bytes(texts)
                artifacts=[dict(name=f,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)) for f,b in [('raw-page-001.txt',raw),('texts.json',texts)]]
                manifest=json.dumps(dict(source='web_public',pages=[dict(url='https://example.test/'+name)],next_urls=[],errors=[],completion=dict(requested_scope_complete=True,omitted_links=0),artifact_files=artifacts)).encode('utf-8')
                (batch/'collection.json').write_bytes(manifest)
                items.append(dict(path=str(batch/'collection.json'),expected_sha256=hashlib.sha256(manifest).hexdigest()))
            config=base/'collections.json'
            config.write_text(json.dumps(dict(collections=items)),encoding='utf-8')
            command=[NODE,str(ROOT/'scripts/merge_public_web.mjs'),str(config),str(base/'merged')]
            result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            merged=json.loads((base/'merged/texts.json').read_text(encoding='utf-8'))
            self.assertEqual(len(merged['records']),2)
            self.assertTrue(merged['web_collection']['complete'])
            sentiment=[NODE,str(ROOT/'scripts/text_sentiment_baseline.mjs'),str(base/'merged/texts.json'),str(base/'analysis')]
            self.assertEqual(subprocess.run(sentiment,capture_output=True).returncode,0)
            (base/'first/raw-page-001.txt').write_text('changed',encoding='utf-8')
            changed=subprocess.run(sentiment[:-1]+[str(base/'analysis-new')],capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(changed.returncode,0)
            self.assertIn('source changed',changed.stderr)

    def test_json_cursor_is_not_guessed_as_a_next_page_url(self):
        code="const m=await import(process.argv[1]);const request=async u=>({status:200,headers:{'content-type':u.endsWith('robots.txt')?'text/plain':'application/json'},bytes:Buffer.from(u.endsWith('robots.txt')?'User-agent: *':JSON.stringify({items:[],next:'opaque-cursor-value'}))});const r=await m.crawlPublicData({urls:['https://example.test/data'],records_pointer:'/items',next_url_pointer:'/next'},{request});console.log(JSON.stringify({next:r.next_urls,issues:r.pagination_issues.length}));"
        result=subprocess.run([NODE,'--input-type=module','-e',code,(ROOT/'scripts/collect_public_web.mjs').as_uri()],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),dict(next=[],issues=1))

    def test_shared_origin_gate_serializes_batches_and_cancels_queued_slot(self):
        code="const m=await import(process.argv[1]);let clock=0;const starts=[];const gate=m.createWebRequestGate({now:()=>clock,wait:async ms=>clock+=ms});await Promise.all([gate.run('https://example.test/a',{},async()=>{starts.push(clock);return {status:200,headers:{}}}),gate.run('https://example.test/b',{},async()=>{starts.push(clock);return {status:200,headers:{}}})]);let release,startedResolve;const started=new Promise(r=>startedResolve=r),held=gate.run('https://held.test/a',{},async()=>{startedResolve();await new Promise(r=>release=r);return {status:200,headers:{}}});await started;let called=false;const c=new AbortController(),cancel=gate.run('https://held.test/b',{signal:c.signal},async()=>{called=true;return {status:200,headers:{}}}).catch(e=>e.name);c.abort();const result=await cancel;release();await held;console.log(JSON.stringify({gap:starts[1]-starts[0],cancelled:result==='AbortError',called,pending:gate.snapshot().pending}));"
        result=subprocess.run([NODE,'--input-type=module','-e',code,(ROOT/'scripts/web_throttle.mjs').as_uri()],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),dict(gap=1000,cancelled=True,called=False,pending=0))

    def test_corpus_and_sentiment_chain_keeps_equal_answers_and_rejects_changed_original(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            source=base/'raw.json'
            source.write_text(json.dumps(dict(source='ai_synthetic',records=[dict(id='a',text=' 满意 '),dict(id='b',text='满意'),dict(id='c',text='  ')]),ensure_ascii=False),encoding='utf-8')
            prep=[NODE,str(ROOT/'scripts/prepare_text_corpus.mjs'),str(source),str(base/'clean')]
            result=subprocess.run(prep,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            clean=json.loads((base/'clean/texts.json').read_text(encoding='utf-8'))
            self.assertEqual(len(clean['records']),2)
            command=[NODE,str(ROOT/'scripts/text_sentiment_baseline.mjs'),str(base/'clean/texts.json'),str(base/'analysis')]
            completed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(completed.returncode,0,completed.stderr)
            analysis=json.loads((base/'analysis/sentiment.json').read_text(encoding='utf-8'))
            self.assertEqual(analysis['cohorts'][0]['counts']['positive'],2)
            self.assertEqual(len(analysis['inputs']),2)
            self.assertTrue((base/'analysis/sentiment.svg').is_file())
            source.write_text('{}',encoding='utf-8')
            changed=subprocess.run(command[:-1]+[str(base/'analysis-new')],capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(changed.returncode,0)
            self.assertIn('source changed',changed.stderr)
