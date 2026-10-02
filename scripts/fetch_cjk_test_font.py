"""Fetch a pinned open Chinese font and its license into an explicit local directory."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

COMMIT = "9710da1eacb3be272583c3224dcb70f9da6eadbb"
BASE = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanssc/"
ASSETS = {
    "NotoSansSC.ttf": (BASE + "NotoSansSC%5Bwght%5D.ttf", "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"),
    "OFL.txt": (BASE + "OFL.txt", "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9"),
}
MAX_BYTES = 32 * 1024 * 1024


def fetch(output: Path) -> Path:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Use a real font directory")
    directory = output.resolve()
    pending = {}
    for name, (url, digest) in ASSETS.items():
        path = directory / name
        if path.is_symlink():
            raise ValueError("Existing font asset must not be a symlink")
        if path.exists():
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Existing {name} has a different hash; choose a new directory")
        else:
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Downloaded {name} failed size/hash verification")
            pending[name] = data
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in pending.items():
        with (directory / name).open("xb") as stream:
            stream.write(data)
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        folder = fetch(args.output)
        print(json.dumps({"font_dir": str(folder), "source_commit": COMMIT, "license": "OFL-1.1", "installed_systemwide": False}))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
