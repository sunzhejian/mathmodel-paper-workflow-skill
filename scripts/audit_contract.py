"""Validate an agent-readable contract and run its PDF audit without editing the PDF."""
import argparse
import json
import math
from pathlib import Path
import sys

import pdf_workflow


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{label} must be a positive integer')
    return value


def number(value, label, minimum, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be finite and numeric')
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{label} is outside the allowed range')
    return value


def local_path(root, value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty project-relative path')
    normalized = value.replace('\\', '/')
    if ':' in normalized or normalized.startswith('/') or '..' in normalized.split('/'):
        raise ValueError(f'{label} must stay inside project root')
    result = (root / normalized).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f'{label} escapes project root through a symlink')
    return result


def make_arguments(contract, root, report, render_dir=None):
    if not isinstance(contract, dict):
        raise ValueError('Contract must be a JSON object')
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Project root must be a directory')
    audit = contract.get('audit')
    if not isinstance(audit, dict):
        raise ValueError('Missing audit object; use the current workflow-contract example')
    pdf = local_path(root, audit.get('pdf'), 'audit.pdf')
    if not pdf.is_file():
        raise ValueError('audit.pdf does not exist; compile the selected source first')
    first = integer(audit.get('first_page', 1), 'audit.first_page')
    last = audit.get('last_page')
    if last is not None:
        integer(last, 'audit.last_page')
        if last < first:
            raise ValueError('audit.last_page is before first_page')
    if audit.get('pdf_scope') not in {'body-only', 'combined'}:
        raise ValueError('audit.pdf_scope must be body-only or combined')
    if audit['pdf_scope'] == 'combined' and last is None:
        raise ValueError('A combined PDF requires last_page to exclude the appendix')
    requirement = contract.get('page_requirement')
    if not isinstance(requirement, dict) or requirement.get('mode') not in {'maximum', 'exact'}:
        raise ValueError('page_requirement.mode must be maximum or exact')
    count = integer(requirement.get('count'), 'page_requirement.count')
    margins = contract.get('margins_cm_top_right_bottom_left')
    if not isinstance(margins, list) or len(margins) != 4:
        raise ValueError('Margins must contain top, right, bottom, left')
    for margin in margins:
        number(margin, 'margin', 0)
    blank = contract.get('blank_limit_percent')
    if blank is not None:
        number(blank, 'blank_limit_percent', 0, 100)
    report_path = local_path(root, report, 'report')
    if report_path == pdf:
        raise ValueError('Report must not overwrite input PDF')
    args = ['audit', str(pdf), '--first-page', str(first),
            '--max-pages' if requirement['mode'] == 'maximum' else '--exact-pages', str(count),
            '--margins-cm', *map(str, margins), '--report', str(report_path)]
    if last is not None:
        args += ['--last-page', str(last)]
    if blank is not None:
        args += ['--blank-limit', str(blank)]
    if render_dir:
        destination = local_path(root, render_dir, 'render-dir')
        # Rendering uses predictable filenames; insist on a new directory.
        if destination.exists():
            raise ValueError('Use a new render-dir to preserve prior previews')
        args += ['--render-dir', str(destination)]
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract')
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--report', default='qa/layout.json', help='Project-relative new JSON report')
    parser.add_argument('--render-dir', help='Project-relative new preview directory')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print arguments without writing outputs')
    args = parser.parse_args(argv)
    try:
        contract_path = Path(args.contract).resolve(strict=True)
        contract = json.loads(contract_path.read_text(encoding='utf-8-sig'))
        command = make_arguments(contract, args.project_root, args.report, args.render_dir)
        report = Path(command[command.index('--report')+1])
        if report == contract_path or report.exists():
            raise ValueError('Use a new report path; existing files are preserved')
        if args.dry_run:
            print(json.dumps({'script': 'pdf_workflow.py', 'arguments': command}, ensure_ascii=False, indent=2))
            return 0
        return pdf_workflow.main(command)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
