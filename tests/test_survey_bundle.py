import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_survey_bundle import check_bundle


class SurveyBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.q = self.file('questionnaire.json', {'questions': [{'id': 'q1', 'text': '测试题'}]})
        self.row = dict(id='fixture-1', source='human_reported', purpose='fieldwork',
                        questionnaire_sha256=self.q['sha256'], answers={'q1': 'a'},
                        quality={'status': 'valid', 'reasons': []})
        self.data = self.file('ledger.json', [self.row])
        self.table = self.file('table.json', {'q1': {'a': 1}, 'n': 1})
        self.bundle = dict(schema_version=1, questionnaire=self.q, datasets=[dict(
            id='actual-batch', source='human_reported', purpose='fieldwork',
            questionnaire_sha256=self.q['sha256'], file=self.data,
            counts={'valid': 1, 'invalid': 0, 'review': 0, 'screened_out': 0})],
            analyses=[dict(method='descriptive', dataset_ids=['actual-batch'], file=self.table)],
            workflow=dict(schema_version=1, checkpoints=[dict(stage='analysis', inputs=[self.q, self.data], outputs=[self.table])]))

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, content):
        data = json.dumps(content, ensure_ascii=False).encode('utf-8')
        (self.root / name).write_bytes(data)
        return dict(path=name, sha256=hashlib.sha256(data).hexdigest())

    def rows(self, rows):
        new = self.file('ledger.json', rows)
        self.bundle['datasets'][0]['file'] = new
        self.bundle['workflow']['checkpoints'][0]['inputs'][1] = new

    def test_fresh_fixture_passes_without_certifying_people_or_science(self):
        result = check_bundle(self.bundle, self.root)
        self.assertTrue(result['current'])
        self.assertEqual(result['datasets'][0]['rows'], 1)
        self.assertFalse(result['authenticity_verified'])
        self.assertFalse(result['scientific_verified'])
        self.assertEqual(result['model_calls'], 0)

    def test_changed_file_stales_analysis_even_when_output_is_untouched(self):
        self.file('ledger.json', [self.row, dict(self.row, id='fixture-2')])
        result = check_bundle(self.bundle, self.root)
        self.assertFalse(result['current'])
        self.assertEqual(result['workflow']['checkpoints'][0]['state'], 'stale')

    def test_ai_cannot_be_relabeled_as_actual_recovery(self):
        self.rows([dict(self.row, source='ai_synthetic', purpose='research')])
        self.assertIn('Source/purpose mismatch: actual-batch', check_bundle(self.bundle, self.root)['issues'])

    def test_quality_counts_and_nonvalid_reasons_are_checked(self):
        self.rows([dict(self.row, quality={'status': 'review', 'reasons': []})])
        issues = check_bundle(self.bundle, self.root)['issues']
        self.assertIn('Excluded/review row requires reasons: actual-batch', issues)
        self.assertIn('Ledger counts mismatch: actual-batch', issues)

    def test_questionnaire_versions_and_duplicate_ids_are_checked(self):
        self.rows([self.row, dict(self.row, questionnaire_sha256='f'*64)])
        issues = check_bundle(self.bundle, self.root)['issues']
        self.assertIn('Missing/duplicate row ID: actual-batch', issues)
        self.assertIn('Row questionnaire mismatch: actual-batch', issues)

    def test_ai_trace_and_source_separated_analysis_are_required(self):
        cohort = dict(id='ai-batch', source='ai_synthetic', purpose='research', questionnaire_sha256=self.q['sha256'],
                      file=self.file('ai.json', [dict(self.row, source='ai_synthetic', purpose='research')]),
                      counts={'valid': 1, 'invalid': 0, 'review': 0, 'screened_out': 0})
        self.bundle['datasets'].append(cohort)
        self.bundle['analyses'][0]['dataset_ids'].append('ai-batch')
        issues = check_bundle(self.bundle, self.root)['issues']
        self.assertIn('Missing AI call receipt fields: ai-batch', issues)
        self.assertIn('Analysis pools different sources/purposes: descriptive', issues)

    def test_same_answer_vector_is_not_automatically_deleted(self):
        self.rows([self.row, dict(self.row, id='fixture-2')])
        self.bundle['datasets'][0]['counts']['valid'] = 2
        self.assertTrue(check_bundle(self.bundle, self.root)['current'])

    def test_cli_is_read_only_and_distinguishes_bad_input(self):
        manifest = self.root / 'bundle.json'
        manifest.write_text(json.dumps(self.bundle), encoding='utf-8')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/check_survey_bundle.py'), str(manifest), '--root', str(self.root)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        bad = copy.deepcopy(self.bundle)
        bad['questionnaire']['path'] = '../outside.json'
        with self.assertRaises(ValueError):
            check_bundle(bad, self.root)


if __name__ == '__main__':
    unittest.main()
