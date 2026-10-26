"""Read-only checks for survey source separation, row ledgers and file freshness.

Does not call a model, clean answers, recompute statistics or certify real people.
Exit 0: recorded contract matches; 1: inconsistent/stale; 2: malformed input.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from check_workflow_state import check_state


def check_bundle(bundle, root):
    root = Path(root).resolve(strict=True)
    if bundle.get('schema_version') != 1:
        raise ValueError('Expected schema_version:1')
    issues, files = [], {}

    def read(item):
        name, expected = item.get('path'), item.get('sha256')
        if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
            raise ValueError('Expected project-relative path')
        if PurePosixPath(name).is_absolute() or any(p in ('', '.', '..') or p.startswith('.') for p in name.split('/')):
            raise ValueError('Unsafe path')
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Expected lowercase SHA256')
        target = root
        for part in name.split('/'):
            target = target / part
            if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
                raise ValueError('Linked paths are not accepted')
        if not target.resolve().is_relative_to(root):
            raise ValueError('Path leaves project')
        if name in files and files[name] != expected:
            raise ValueError('Conflicting fingerprint for '+name)
        files[name] = expected
        try:
            data = target.read_bytes()
        except FileNotFoundError:
            issues.append('Missing file: '+name)
            return None
        if hashlib.sha256(data).hexdigest() != expected:
            issues.append('Changed file: '+name)
            return None
        return data

    questionnaire = bundle.get('questionnaire')
    if not isinstance(questionnaire, dict):
        raise ValueError('Expected questionnaire file fingerprint')
    questionnaire_bytes = read(questionnaire)
    if questionnaire_bytes is not None:
        questions = json.loads(questionnaire_bytes).get('questions')
        if not isinstance(questions, list) or not questions:
            raise ValueError('Expected saved questionnaire with questions')
        ids = [q.get('id') for q in questions]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Question IDs must be unique')
    datasets = bundle.get('datasets')
    if not isinstance(datasets, list) or not 1 <= len(datasets) <= 100:
        raise ValueError('Expected 1-100 datasets')
    cohorts, results = {}, []
    for dataset in datasets:
        ident, source, purpose = (dataset.get(k) for k in ('id', 'source', 'purpose'))
        if not isinstance(ident, str) or not ident or ident in cohorts:
            raise ValueError('Dataset IDs must be unique')
        if (source, purpose) not in [('human_reported', 'fieldwork'), ('ai_synthetic', 'research'), ('ai_synthetic', 'pilot')]:
            raise ValueError('Unknown source/purpose pair')
        cohorts[ident] = (source, purpose)
        data = read(dataset['file'])
        if dataset.get('questionnaire_sha256') != questionnaire['sha256']:
            issues.append('Questionnaire version mismatch: '+ident)
        if data is None:
            continue
        rows = json.loads(data)
        if not isinstance(rows, list):
            raise ValueError('Dataset must be a JSON array')
        counts = {k: 0 for k in ('valid', 'invalid', 'review', 'screened_out')}
        seen = set()
        for row in rows:
            row_id = row.get('id')
            if not isinstance(row_id, str) or not row_id or row_id in seen:
                issues.append('Missing/duplicate row ID: '+ident)
            seen.add(row_id)
            if row.get('source') != source or row.get('purpose') != purpose:
                issues.append('Source/purpose mismatch: '+ident)
            if row.get('questionnaire_sha256') != questionnaire['sha256']:
                issues.append('Row questionnaire mismatch: '+ident)
            quality = row.get('quality', {})
            status = quality.get('status')
            if status not in counts:
                issues.append('Missing quality status: '+ident)
            else:
                counts[status] += 1
                reasons = quality.get('reasons')
                if status != 'valid' and (not isinstance(reasons, list) or not reasons or any(not isinstance(r, str) or not r.strip() for r in reasons)):
                    issues.append('Excluded/review row requires reasons: '+ident)
            if source == 'ai_synthetic':
                trace = row.get('provenance', {})
                if any(not isinstance(trace.get(k), str) or not trace[k].strip() for k in ('model', 'request_id', 'prompt_sha256')):
                    issues.append('Missing AI call receipt fields: '+ident)
        if dataset.get('counts') != counts:
            issues.append('Ledger counts mismatch: '+ident)
        results.append(dict(id=ident, source=source, purpose=purpose, rows=len(rows), counts=counts))
    analyses = bundle.get('analyses', [])
    if not isinstance(analyses, list):
        raise ValueError('Expected analyses array')
    for analysis in analyses:
        if not isinstance(analysis.get('method'), str) or not analysis['method'].strip():
            raise ValueError('Analysis requires method')
        selected = analysis.get('dataset_ids')
        if not isinstance(selected, list) or not selected or any(d not in cohorts for d in selected):
            raise ValueError('Analysis refers to unknown datasets')
        if len({cohorts[d] for d in selected}) != 1:
            issues.append('Analysis pools different sources/purposes: '+analysis['method'])
        read(analysis['file'])
    workflow = bundle.get('workflow')
    freshness = check_state(workflow, root) if workflow is not None else None
    if freshness is not None and not freshness['current']:
        issues.append('Workflow dependencies are stale')
    return dict(schema_version=1, current=not issues, issues=issues, datasets=results,
                checked_files=len(files), workflow=freshness, model_calls=0,
                authenticity_verified=False, scientific_verified=False,
                scope='recorded_sources_counts_file_hashes_and_dependencies_only')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check_bundle(json.loads(args.bundle.read_text(encoding='utf-8')), args.root)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['current'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
