"""Create a new MathorCup Big Data draft; preserve existing paper/configuration."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(engine: str, output: Path, skill_root: Path = ROOT) -> Path:
    if engine not in {"latex", "typst"}:
        raise ValueError("engine must be latex or typst")
    source = skill_root / "assets/templates/zh" / ("mathorcup-bigdata-latex" if engine == "latex" else "mathorcup-bigdata")
    entry = source / ("main.tex" if engine == "latex" else "main.typ")
    if not entry.is_file():
        raise ValueError("MathorCup Big Data adaptation is missing")
    destination = output.resolve()
    if output.is_symlink() or destination.exists():
        raise ValueError("Use a new output directory; existing files/configuration are preserved")
    if destination == source.resolve() or destination.is_relative_to(source.resolve()):
        raise ValueError("Output cannot be inside the template source")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Template source must not contain symlinks")
    shutil.copytree(source, destination)
    return destination / entry.name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("latex", "typst"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        entry = prepare(args.engine, args.output)
        print(f"Created Big Data draft: {entry}")
        print("2026 preparation; paper-format baseline is 2025. Confirm current rules before submission.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
