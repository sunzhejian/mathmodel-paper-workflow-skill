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
