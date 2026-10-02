"""Compile/render anonymous synthetic template probes, never a contest solution."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("latex", "typst"), required=True)
    parser.add_argument("--compiler", help="Existing XeLaTeX/Typst executable; no automatic installation")
    parser.add_argument("--font-path", type=Path, help="Existing Chinese font directory for the Typst probe")
    parser.add_argument("--output", type=Path, required=True, help="New synthetic probe directory")
    args = parser.parse_args(argv)
    try:
        compiler = args.compiler or os.environ.get("MATHMODEL_XELATEX_EXE" if args.engine == "latex" else "MATHMODEL_TYPST_EXE") or shutil.which("xelatex" if args.engine == "latex" else "typst")
        if not compiler:
            raise ValueError("Select an existing compiler")
        prepare = load(ROOT / "scripts/prepare_mathorcup_bigdata_template.py")
        check = load(ROOT / "scripts/check_mathorcup_bigdata_pdf.py")
        fixture = load(ROOT / "tests/bigdata_fixture.py")
        entry = prepare.prepare(args.engine, args.output)
        folder = entry.parent
        build = folder / "build"
        build.mkdir()
        fixture.fill(folder, args.engine, appendix=True, ai=True)
        def run(command):
            value = subprocess.run(command, cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if value.returncode:
                raise ValueError((value.stdout + value.stderr)[-3000:])
            return value.stdout
        if args.engine == "latex":
            version = run([compiler, "--version"])
            flags = ["--disable-installer"] if "MiKTeX" in version else []
            for _ in range(3):
                run([compiler, *flags, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "-output-directory=build", entry.name])
        else:
            fonts = args.font_path.resolve(strict=True) if args.font_path else fixture.font_dir(folder)
            font_args = ["--ignore-system-fonts", "--font-path", str(fonts)] if fonts else []
            run([compiler, "compile", *font_args, entry.name, "build/main.pdf"])
            metadata = run([compiler, "query", *font_args, entry.name, "<bd-boundary>", "--field", "value", "--one"])
            (build / "main.bigdata.json").write_text(metadata, encoding="utf-8")
        report = check.verify(build / "main.pdf", build / "main.bigdata.json", expected_year=2026)
        (build / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        with pymupdf.open(build / "main.pdf") as doc:
            for i, page in enumerate(doc, 1):
                page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(build / f"page-{i:02}.png")
        print(json.dumps({"synthetic_fixture": True, "engine": args.engine, "pdf": str(build / "main.pdf"),
                          "passed": report["passed"], "total_pages": report["total_pages"],
                          "body_pages": report["body_pages"], "rules_status": report["rules_status"],
                          "failures": report["failures"]}, ensure_ascii=False))
        return 0 if report["passed"] else 1
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
