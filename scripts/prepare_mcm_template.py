"""Copy a project-owned MCM template into a new directory; never overwrite a project."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(engine: str, output: Path, skill_root: Path = ROOT) -> Path:
    if engine not in {"latex", "typst"}:
        raise ValueError("engine must be latex or typst")
    source = skill_root/"assets/templates/en"/("mcm-latex" if engine == "latex" else "mcm")
    entry = source/("main.tex" if engine == "latex" else "main.typ")
    if not entry.is_file():
        raise ValueError("Project-owned MCM template is missing")
    destination = output.resolve()
    if output.is_symlink() or destination.exists():
        raise ValueError("Use a new output directory; existing files and configuration are preserved")
    if destination == source.resolve() or destination.is_relative_to(source.resolve()):
        raise ValueError("Output cannot be inside the template source")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Template source must not contain symlinks")
    shutil.copytree(source, destination)
    return destination/entry.name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("latex", "typst"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        entry = prepare(args.engine, args.output)
        print(f"Created MCM template: {entry}")
        print("Fill config, summary, solution and references; enable AI report according to actual use.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
