"""Run a synthetic, offline end-to-end workflow; never overwrites an output folder."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

import fitz

ROOT = Path(__file__).resolve().parents[1]
SOLVER = '''"""Synthetic analytic example; not experimental or competition data."""
import csv
import math
from pathlib import Path

output = Path(__file__).resolve().parents[1] / "results" / "series.csv"
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["time", "synthetic_y"])
    for t in range(21):
        writer.writerow([t, repr(math.exp(-0.2 * t))])
print(output)
'''


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def command(script, arguments, expected=0):
    proc = subprocess.run([sys.executable, str(script), *map(str, arguments)],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    if proc.returncode != expected:
        raise RuntimeError(f'{script.name}: expected {expected}, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}')
    return {'script': script.name, 'exit_code': proc.returncode, 'expected': expected}


def fixture_pdf(path, labels, values, sparse=False, raw=False):
    with fitz.open() as doc:
        for label in labels:
            page = doc.new_page(width=595, height=842)
            page.insert_text((75, 90), label, fontsize=15)
            if not sparse:
                page.insert_text((75, 120), 'SYNTHETIC fixture: y(t) = exp(-0.2 t). No empirical claim.', fontsize=10)
                for i, (t, y) in enumerate(values):
                    page.insert_text((75, 155 + i*24), f't={t:2d}   y={y:.12f}', fontsize=11)
                for i, line in enumerate([
                    'Input: integer samples 0..20; rate 0.2; deterministic analytic evaluation.',
                    'Evidence: full-precision CSV; fixed display format; no fitted observations.',
                    'Verification: endpoint values and monotonicity checked by the runner.',
                    'This page tests document tools; it is not a proposed paper layout.',
                    'Visual checks and domain validation remain separate tasks.'
                ]):
                    page.insert_text((75, 680 + i*17), line, fontsize=10)
            if raw:
                page.insert_text((75, 770), r'\frac{x}{y}', fontsize=11)
        doc.save(path)


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    support = output/'support'
    (support/'code').mkdir(parents=True)
    solver = support/'code'/'problem1.py'
    solver.write_text(SOLVER, encoding='utf-8')
    calls = [command(solver, [])]
    with (support/'results'/'series.csv').open(encoding='utf-8') as stream:
        rows = [(int(row['time']), float(row['synthetic_y'])) for row in csv.DictReader(stream)]
    if len(rows) != 21 or rows[0] != (0, 1.0) or not math.isclose(rows[-1][1], math.exp(-4), rel_tol=1e-14):
        raise RuntimeError('Synthetic solver endpoint check failed')
    if not all(a[1] > b[1] for a, b in zip(rows, rows[1:])):
        raise RuntimeError('Synthetic solver monotonicity check failed')
    fixture_pdf(output/'body.pdf', ['Synthetic body - 1', 'Synthetic body - 2'], rows)
    fixture_pdf(output/'original.pdf', ['Old body', 'Protected appendix A', 'Protected appendix B'], rows)
    fixture_pdf(output/'bad-whitespace.pdf', ['Deliberately sparse negative fixture'], rows, sparse=True)
    fixture_pdf(output/'bad-formula.pdf', ['Deliberately uncompiled negative fixture'], rows, raw=True)
    original_hash = hashlib.sha256((output/'original.pdf').read_bytes()).hexdigest()
    pdf = ROOT/'scripts'/'pdf_workflow.py'
    calls.append(command(pdf, ['audit', output/'body.pdf', '--exact-pages', 2, '--blank-limit', 20,
                               '--report', output/'layout.json', '--render-dir', output/'pages']))
    for name in ['bad-whitespace', 'bad-formula']:
        calls.append(command(pdf, ['audit', output/f'{name}.pdf', '--blank-limit', 20,
                                   '--report', output/f'{name}.json'], expected=1))
    bad_blank = json.loads((output/'bad-whitespace.json').read_text(encoding='utf-8'))
    bad_formula = json.loads((output/'bad-formula.json').read_text(encoding='utf-8'))
    if not any('blank band' in x for x in bad_blank['failures']):
        raise RuntimeError('Whitespace counterexample was not detected')
    if not any('formula' in x for x in bad_formula['failures']):
        raise RuntimeError('Formula counterexample was not detected')
    calls.append(command(pdf, ['append', output/'body.pdf', output/'original.pdf', output/'final.pdf',
                               '--appendix-start', 2, '--number-pages', '--report', output/'appendix.json']))
    if original_hash != hashlib.sha256((output/'original.pdf').read_bytes()).hexdigest():
        raise RuntimeError('Original PDF changed')
    appendix = json.loads((output/'appendix.json').read_text(encoding='utf-8'))
    if appendix['total_pages'] != 4 or appendix['appendix_pages_verified'] != 2 or appendix['appendix_number_range'] != [3, 4]:
        raise RuntimeError('Appendix validation summary is unexpected')
    whitelist = [{'path': 'code/problem1.py', 'description': 'Independent synthetic analytic solver'},
                 {'path': 'results/series.csv', 'description': 'Full-precision synthetic values; not measured data'}]
    write_json(output/'support-files.json', whitelist)
    calls.append(command(ROOT/'scripts'/'package_support.py', [support, output/'support-files.json', output/'support.zip']))
    with zipfile.ZipFile(output/'support.zip') as archive:
        if set(archive.namelist()) != {'code/problem1.py', 'results/series.csv', 'MANIFEST.json'}:
            raise RuntimeError('Unexpected support package files')
    report = {'passed': True, 'data_kind': 'synthetic analytic example, not competition data',
              'python': sys.version, 'rows': len(rows), 'total_pages': 4,
              'appendix_pages_verified': 2, 'original_unchanged': True,
              'expected_rejections': {'whitespace': bad_blank['failures'], 'formula': bad_formula['failures']},
              'commands': calls}
    write_json(output/'demo-report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New output directory; existing directories are rejected')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
