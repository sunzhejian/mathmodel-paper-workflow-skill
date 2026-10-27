"""Supervised text sentiment with an explicit held-out evaluation. No model downloads.

Run with code/text-sentiment-config.json in project cwd. Needs scikit-learn.
Labels must come from a separately reviewed training file, never the target texts.
"""
import csv
import hashlib
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
import sklearn


def run(config, root=Path('.')):
    root = root.resolve()
    def source(name):
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Input must be a real project file')
        raw = path.read_bytes()
        return json.loads(raw.decode('utf-8-sig')), hashlib.sha256(raw).hexdigest()
    train, train_sha = source(config['training_path'])
    target, input_sha = source(config['input_path'])
    if train.get('label_source') != 'human_reviewed':
        raise ValueError('Training labels require separately recorded human review')
    rows, texts = train['records'], target['records']
    if not rows or not texts or any(not isinstance(r.get('text'), str) or not r['text'].strip() or r.get('label') not in ['positive', 'negative', 'neutral'] for r in rows):
        raise ValueError('Training records require text and positive/negative/neutral labels')
    if len({r['id'] for r in rows}) != len(rows) or len({r['id'] for r in texts}) != len(texts):
        raise ValueError('Record ids must be unique')
    fingerprints = [hashlib.sha256(r['text'].strip().encode()).hexdigest() for r in rows]
    if len(set(fingerprints)) != len(rows):
        raise ValueError('Duplicate training texts must be reviewed/grouped before splitting')
    if set(fingerprints) & {hashlib.sha256(r['text'].strip().encode()).hexdigest() for r in texts}:
        raise ValueError('Prediction target overlaps training data')
    labels = sorted({r['label'] for r in rows})
    if len(labels) < 2 or min(sum(r['label'] == k for r in rows) for k in labels) < 5:
        raise ValueError('Need at least two classes and five reviewed examples per class')
    groups = [r.get('group') for r in rows]
    if any(g is not None for g in groups):
        raise ValueError('Grouped users/documents require a separately designed group-aware split')
    indices = list(range(len(rows)))
    fit, holdout = train_test_split(indices, test_size=config.get('test_size', .25), random_state=config.get('seed', 17), stratify=[r['label'] for r in rows])
    model = Pipeline([('tfidf', TfidfVectorizer(analyzer='char', ngram_range=(2, 4), max_features=50000)), ('classifier', LogisticRegression(max_iter=1000, class_weight='balanced', random_state=config.get('seed', 17)))])
    model.fit([rows[i]['text'] for i in fit], [rows[i]['label'] for i in fit])
    actual = [rows[i]['label'] for i in holdout]
    predicted = model.predict([rows[i]['text'] for i in holdout]).tolist()
    evaluations = dict(classification_report=classification_report(actual, predicted, labels=labels, output_dict=True, zero_division=0), confusion_matrix=confusion_matrix(actual, predicted, labels=labels).tolist(), labels=labels, train_ids=[rows[i]['id'] for i in fit], holdout_ids=[rows[i]['id'] for i in holdout])
    out = (root / config.get('output_dir', 'results/text-sentiment-supervised')).resolve()
    if not out.is_relative_to(root) or out.exists():
        raise ValueError('Choose a new output folder inside the project')
    out.mkdir(parents=True)
    from joblib import dump
    model_path = out / 'sentiment-model.joblib'
    dump(model, model_path)
    result = dict(model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(), method='char-tfidf-logistic-regression', sklearn_version=sklearn.__version__, input_sha256=input_sha, training_sha256=train_sha, label_source='user_declared_human_reviewed', evaluations=evaluations, score_is_calibrated=False, model_refit_on_holdout=False, predictions=[dict(id=r['id'], source=r.get('source'), label=str(label)) for r, label in zip(texts, model.predict([r['text'] for r in texts]))])
    (out / 'sentiment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    config = json.loads(Path('code/text-sentiment-config.json').read_text(encoding='utf-8-sig'))
    result = run(config)
    print(json.dumps(dict(method=result['method'], predicted=len(result['predictions']), holdout=len(result['evaluations']['holdout_ids']), macro_f1=result['evaluations']['classification_report']['macro avg']['f1-score'])))
