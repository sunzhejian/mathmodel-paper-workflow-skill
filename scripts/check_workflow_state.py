"""Check recorded workflow fingerprints; does not execute or certify science."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def check_state(state, root):
    root = Path(root).resolve(strict=True)
    if state.get('schema_version') != 1 or not isinstance(state.get('checkpoints'), list):
        raise ValueError('Expected schema_version:1 and checkpoints array')
    if len(state['checkpoints']) > 24:
        raise ValueError('At most 24 stages')
    stages, seen, cache = [], set(), {}
    def digest(item):
        name = item.get('path')
        expected = item.get('sha256')
        if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
            raise ValueError('Invalid project-relative path')
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(p in ('', '.', '..') or p.startswith('.') for p in name.split('/')):
            raise ValueError('Invalid project-relative path')
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Expected lowercase SHA256')
        target = root.joinpath(*relative.parts)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
                raise ValueError('Linked paths are not accepted')
        if not target.resolve().is_relative_to(root):
            raise ValueError('Path leaves project root')
        if name not in cache:
            try:
                with target.open('rb') as stream:
                    h = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        h.update(chunk)
                    cache[name] = h.hexdigest()
            except (FileNotFoundError, IsADirectoryError):
                cache[name] = None
        return cache[name] == expected
    for raw in state['checkpoints']:
        stage = raw.get('stage')
        if not isinstance(stage, str) or not stage.strip() or stage in seen:
            raise ValueError('Each stage must have a unique nonempty name')
        seen.add(stage)
        inputs, outputs = raw.get('inputs'), raw.get('outputs')
        if not all(isinstance(items, list) and 1 <= len(items) <= 32 and all(isinstance(f, dict) for f in items) for items in (inputs, outputs)):
            raise ValueError('Expected 1-32 inputs and outputs per stage')
        paths = [f.get('path') for f in inputs + outputs]
        if any(not isinstance(p, str) for p in paths) or len(set(paths)) != len(paths):
            raise ValueError('Inputs and outputs must be distinct')
        changed = [f['path'] for f in inputs + outputs if not digest(f)]
        stages.append(dict(stage=stage, inputs=inputs, outputs=outputs, state='stale' if changed else 'current', changed=changed, upstream_stages=[]))
    for _ in stages:
        added = False
        for stage in stages:
            for parent in stages:
                if stage is parent or parent['state'] != 'stale' or parent['stage'] in stage['upstream_stages']:
                    continue
                if any(i == o for i in stage['inputs'] for o in parent['outputs']):
                    stage['upstream_stages'].append(parent['stage'])
                    stage['state'] = 'stale'
                    added = True
        if not added:
            break
    return dict(schema_version=1, current=all(s['state'] == 'current' for s in stages), checkpoints=stages, scientific_verified=False, scope='file_fingerprints_and_recorded_dependencies_only')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state', type=Path)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check_state(json.loads(args.state.read_text(encoding='utf-8')), args.root)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['current'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
