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


@unittest.skipUnless(NODE, 'Node.js is required for the standalone wordcloud CLI')
class WordcloudTests(unittest.TestCase):
    def test_files_match_manifest_and_keep_source_negation_and_redacted_context(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'input.json'
            source.write_text(json.dumps(dict(dataset='ai', question_id='Q15', records=[
                dict(id='b', text='不付费 人工复核 联系13800138000'),
                dict(id='a', text='人工复核 人工复核 隐私保护')]), ensure_ascii=False), encoding='utf-8')
            before = source.read_bytes()
            run = subprocess.run([NODE, str(ROOT / 'scripts/survey_wordcloud.mjs'), '--input', str(source), '--out', str(base / 'out')], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads((base / 'out/wordcloud.json').read_text(encoding='utf-8'))
            terms = {t['word']: t for t in data['terms']}
            self.assertEqual(terms['人工复核']['documents'], 2)
            self.assertEqual(terms['人工复核']['occurrences'], 3)
            self.assertIn('不付费', terms)
            self.assertEqual(data['dataset'], 'ai')
            self.assertNotIn('13800138000', json.dumps(data['contexts'], ensure_ascii=False))
            manifest = json.loads((base / 'out/manifest.json').read_text(encoding='utf-8'))
            for item in manifest['files']:
                self.assertEqual(hashlib.sha256((base / 'out' / item['path']).read_bytes()).hexdigest(), item['sha256'])
            self.assertEqual(source.read_bytes(), before)
            repeated = subprocess.run(run.args, capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn('Output exists', repeated.stderr)

    def test_declared_ai_source_cannot_be_relabelled_real(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.json'
            source.write_text(json.dumps(dict(dataset='ai', records=[dict(id='a', text='人工复核')])), encoding='utf-8')
            out = Path(folder) / 'out'
            run = subprocess.run([NODE, str(ROOT / 'scripts/survey_wordcloud.mjs'), '--input', str(source), '--out', str(out), '--dataset', 'real'], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('must not relabel', run.stderr)
            self.assertFalse(out.exists())
