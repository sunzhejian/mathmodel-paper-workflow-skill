import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('sklearn'), 'optional scikit-learn training runtime')
class TextSentimentTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('text_sentiment', ROOT / 'scripts/text_sentiment.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_training_keeps_holdout_disjoint_and_saves_model_without_claiming_corpus_accuracy(self):
        module = self.load()
        positive = ['This useful service saves time', 'I love the clear interface', 'A reliable tool for routine work', 'Helpful support and easy controls', 'Excellent answers to simple tasks', 'Convenient access to shared notes', 'Good design with simple menus', 'A pleasant and efficient workflow', 'The tool is practical and helpful', 'I am satisfied with its speed']
        negative = ['This service is confusing and slow', 'I dislike the broken interface', 'Unreliable output needs repeated correction', 'Unhelpful support and difficult controls', 'Terrible errors in simple tasks', 'Access to the notes keeps failing', 'Bad design with complex menus', 'An unpleasant and inefficient workflow', 'The tool is impractical and frustrating', 'I am disappointed with its quality']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = [dict(id='p'+str(i), text=s, label='positive') for i, s in enumerate(positive)] + [dict(id='n'+str(i), text=s, label='negative') for i, s in enumerate(negative)]
            (root/'training.json').write_text(json.dumps(dict(label_source='human_reviewed', fixture_only=True, records=records)), encoding='utf-8')
            (root/'target.json').write_text(json.dumps(dict(records=[dict(id='x', text='Support was good but the interface was confusing', source='fixture_only')])), encoding='utf-8')
            result = module.run(dict(training_path='training.json', input_path='target.json'), root)
            evaluation = result['evaluations']
            self.assertFalse(set(evaluation['train_ids']) & set(evaluation['holdout_ids']))
            self.assertEqual(len(evaluation['train_ids'])+len(evaluation['holdout_ids']), 20)
            self.assertTrue((root/'results/text-sentiment-supervised/sentiment-model.joblib').is_file())
            self.assertFalse(result['score_is_calibrated'])
            self.assertFalse(result['model_refit_on_holdout'])
            self.assertIn('macro avg', evaluation['classification_report'])
            self.assertEqual(result['predictions'][0]['source'], 'fixture_only')

    def test_training_rejects_auto_labels_and_copied_target_text(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'train.json').write_text(json.dumps(dict(label_source='model_generated', records=[])), encoding='utf-8')
            (root/'target.json').write_text(json.dumps(dict(records=[])), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'human review'):
                module.run(dict(training_path='train.json', input_path='target.json'), root)


if __name__ == '__main__':
    unittest.main()
