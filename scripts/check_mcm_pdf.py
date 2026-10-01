"""Verify MCM summary, page boundaries and headers against compiled sidecar metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import pymupdf as fitz


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            value.update(block)
    return value.hexdigest()


def normalized(text: str) -> str:
    text = re.sub(r"\u00ad\s*", "", text).replace("\u2060", "")
    return re.sub(r"\s+", " ", text).strip()


def verify(pdf_path: Path, metadata_path: Path, max_solution_pages: int = 25,
           expected_year: int | None = None) -> dict:
    if type(max_solution_pages) is not int or max_solution_pages < 1:
        raise ValueError("max-solution-pages must be a positive integer")
    meta = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if not isinstance(meta, dict) or type(meta.get("schema_version")) is not int or meta["schema_version"] != 1 or meta.get("family") != "mcm-icm":
        raise ValueError("Use compiled MCM schema_version 1 metadata")
    for key in ("contest_year", "summary_last_page", "solution_last_page", "total_pages"):
        if type(meta.get(key)) is not int:
            raise ValueError(f"MCM metadata requires integer {key}")
    ai_first = meta.get("ai_first_page")
    if ai_first is not None and type(ai_first) is not int:
        raise ValueError("ai_first_page must be integer or null")
    team = meta.get("team_control_number")
    if not isinstance(team, str) or not re.fullmatch(r"[0-9]{1,20}", team):
        raise ValueError("MCM metadata requires a numeric team_control_number string")
    failures = []
    if set(team) == {"0"}:
        failures.append("Team control number is still a template placeholder")
    if not isinstance(meta.get("problem"), str) or meta["problem"] not in {"A", "B", "C", "D", "E", "F"}:
        failures.append("Problem selection is unfilled or invalid")
    if expected_year is not None and meta["contest_year"] != expected_year:
        failures.append("Contest year differs from the selected edition")
    with fitz.open(pdf_path) as document:
        total = len(document)
        solution_end = meta["solution_last_page"]
        summary_end = meta["summary_last_page"]
        if meta["total_pages"] != total:
            failures.append("Compiled total-page metadata differs from PDF")
        if summary_end != 1:
            failures.append("Summary Sheet must occupy exactly the first page")
        if not 1 <= solution_end <= total:
            failures.append("Invalid solution end boundary")
        if solution_end > max_solution_pages:
            failures.append("Solution exceeds the selected page limit")
        if ai_first is None:
            if solution_end != total:
                failures.append("Pages after solution are not identified as an AI report")
        elif ai_first != solution_end + 1 or not 1 <= ai_first <= total:
            failures.append("AI report must start immediately after the solution")
        elif "Report on Use of AI Tools" not in normalized(document[ai_first-1].get_text()):
            failures.append("AI boundary page has no Report on Use of AI Tools heading")
        sheet_pages = []
        header_records = []
        for index, page in enumerate(document):
            text = normalized(page.get_text())
            if index < solution_end and all(token in text for token in ("Problem Chosen", "Summary Sheet", "Team Control Number")):
                sheet_pages.append(index+1)
            if index < solution_end and re.search(r"\bREPLACE_[A-Z_]+", text):
                failures.append(f"Page {index+1}: unfilled template content")
            if index >= solution_end and "REPLACE_AI_REPORT" in text:
                failures.append(f"Page {index+1}: AI report is still a placeholder")
            header = normalized(page.get_text(clip=fitz.Rect(0, 0, page.rect.width, page.rect.height*0.12)))
            team_ok = re.search(r"\bTeam\s*#?\s*"+re.escape(team)+r"(?!\d)", header) is not None
            page_match = re.search(r"\bPage\s+(\d+)(?:\s+of\s+(\d+))?", header)
            page_ok = bool(page_match and int(page_match[1]) == index+1)
            total_ok = bool(page_match and (page_match[2] is None or int(page_match[2]) == total))
            header_records.append({"page": index+1, "team_matches": team_ok,
                                   "page_number_matches": page_ok, "header_total_matches": total_ok})
            if not team_ok:
                failures.append(f"Page {index+1}: required team header is missing or mismatched")
            if not page_ok or not total_ok:
                failures.append(f"Page {index+1}: header page number or total is wrong")
        if sheet_pages != [1]:
            failures.append("Expected one Summary Sheet on physical page 1")
        return {"passed": not failures, "contest_year": meta["contest_year"],
                "problem": meta.get("problem"), "total_pages": total,
                "solution_pages": solution_end, "summary_last_page": summary_end,
                "ai_report_pages": total-solution_end if ai_first is not None else 0,
                "max_solution_pages": max_solution_pages, "headers": header_records,
                "pdf_sha256": file_hash(pdf_path), "metadata_sha256": file_hash(metadata_path),
                "failures": failures,
                "scope": "Compiled boundaries, summary presence, headers and scaffold markers only; not mathematical correctness, font/visual QA, citations, AI-use truth or official adjudication"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="New JSON report; never overwrites inputs")
    parser.add_argument("--max-solution-pages", type=int, default=25)
    parser.add_argument("--year", type=int)
    args = parser.parse_args(argv)
    try:
        report = args.report.resolve()
        if report.exists() or report in {args.pdf.resolve(), args.metadata.resolve()}:
            raise ValueError("Use a new report path distinct from input files")
        result = verify(args.pdf, args.metadata, args.max_solution_pages, args.year)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({"passed": result["passed"], "solution_pages": result["solution_pages"],
                          "ai_report_pages": result["ai_report_pages"], "failures": result["failures"]}, ensure_ascii=False))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
