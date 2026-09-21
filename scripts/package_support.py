"""Build a verified support ZIP from an explicit JSON allowlist."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

DENIED = {'.git', '.venv', 'venv', '__pycache__', '.ssh', '.env', '.codex', '.mathmodel', 'node_modules'}


def digest(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024*1024), b''):
        h.update(block)
    return h.hexdigest()


def build(root, list_path, output):
    root, list_path, output = Path(root).resolve(), Path(list_path).resolve(), Path(output).resolve()
    if not root.is_dir() or output.exists():
        raise ValueError('Root must exist and output ZIP must be new')
    items = json.loads(list_path.read_text(encoding='utf-8'))
    if not isinstance(items, list) or not items:
        raise ValueError('Allowlist must be a nonempty JSON array')
    names, files, records = set(), [], []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('description'), str):
            raise ValueError('Each item needs string path and description')
        name = item['path'].replace('\\', '/')
        path = PurePosixPath(name)
        parts = [part.lower() for part in path.parts]
        if path.is_absolute() or '..' in parts or ':' in name or not path.parts:
            raise ValueError(f'Unsafe relative path: {name}')
        name = path.as_posix()
        if any(p in DENIED or p.startswith('.env.') for p in parts) or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}:
            raise ValueError(f'Private/cache file excluded: {name}')
        if name.casefold() in names or name.casefold() == 'manifest.json':
            raise ValueError(f'Duplicate/reserved archive name: {name}')
        names.add(name.casefold())
        file = root.joinpath(*path.parts)
        if file.is_symlink() or any(p.is_symlink() for p in file.parents if p != root and p.is_relative_to(root)):
            raise ValueError(f'Symlink entry excluded: {name}')
        file = file.resolve()
        if not file.is_relative_to(root) or not file.is_file() or file == output:
            raise ValueError(f'Missing or out-of-root file: {name}')
        with file.open('rb') as stream:
            h = digest(stream)
        files.append((file, name))
        records.append({'path': name, 'description': item['description'], 'size': file.stat().st_size, 'sha256': h})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for file, name in files:
            z.write(file, name)
        z.writestr('MANIFEST.json', json.dumps({'files': records}, ensure_ascii=False, indent=2))
    try:
        with zipfile.ZipFile(output) as z:
            for record in records:
                with z.open(record['path']) as stream:
                    if digest(stream) != record['sha256']:
                        raise ValueError('ZIP content differs from manifest')
    except Exception:
        # Remove only the newly created failed output, never source material.
        output.unlink()
        raise
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('allowlist'); p.add_argument('output')
    args = p.parse_args()
    try:
        records = build(args.root, args.allowlist, args.output)
        print(json.dumps({'files_verified': len(records), 'output': str(Path(args.output).resolve())}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
