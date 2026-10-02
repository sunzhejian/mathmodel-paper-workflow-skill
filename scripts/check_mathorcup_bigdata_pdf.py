"""Check compiled Big Data layout against the explicitly dated 2025 format baseline."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import pymupdf as fitz


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def verify(pdf_path: Path, metadata_path: Path, max_body_pages: int = 30, expected_year: int | None = None) -> dict:
    if type(max_body_pages) is not int or max_body_pages < 1:
        raise ValueError("max-body-pages must be a positive integer")
    meta = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if not isinstance(meta, dict) or meta.get("family") != "mathorcup-bigdata" or type(meta.get("schema_version")) is not int or meta["schema_version"] != 1:
        raise ValueError("Use compiled MathorCup Big Data schema_version 1 metadata")
    for key in ("contest_year", "format_rules_year", "summary_last_page", "contents_last_page", "body_first_page", "body_last_page", "total_pages"):
        if type(meta.get(key)) is not int:
            raise ValueError(f"Metadata requires integer {key}")
    appendix = meta.get("appendix_first_page")
    if appendix is not None and type(appendix) is not int:
        raise ValueError("appendix_first_page must be integer or null")
    team = meta.get("team_number")
    if not isinstance(team, str):
        raise ValueError("team_number must be a string")
    track = meta.get("track")
    if not isinstance(track, str):
        raise ValueError("track must be a string")
    failures = []
    if not re.fullmatch(r"MCB\d{7}", team) or not team.startswith(f"MCB{meta['contest_year'] % 100:02}"):
        failures.append("Anonymous team number is unfilled or differs from the selected edition")
    if track not in {"A", "B"}:
        failures.append("Track must be the selected A or B problem")
    if expected_year is not None and meta["contest_year"] != expected_year:
        failures.append("Contest year differs from the selected edition")
    if meta["format_rules_year"] != 2025 or meta.get("rules_status") != "provisional":
        failures.append("Format baseline/status differs from this adaptation; verify the new rule source separately")
    with fitz.open(pdf_path) as doc:
        total = len(doc)
        first, last = meta["body_first_page"], meta["body_last_page"]
        if meta["total_pages"] != total:
            failures.append("Compiled total-page metadata differs from PDF")
        if meta["summary_last_page"] != 1:
            failures.append("Title, abstract and keywords must fit physical page 1")
        if meta["contents_last_page"] != 2 or first != 3:
            failures.append("Contents must occupy physical page 2 and body must start on page 3")
        valid_body = 3 <= first <= last <= total
        if not valid_body:
            failures.append("Invalid body boundary")
        body_pages = last - first + 1 if valid_body else None
        if body_pages is not None and body_pages > max_body_pages:
            failures.append("Body exceeds the selected page limit")
        if appendix is None:
            if last != total:
                failures.append("Pages after body have no declared appendix boundary")
        elif appendix != last + 1 or not 1 <= appendix <= total:
            failures.append("Appendix must start immediately after body")
        elif "附录" not in compact(doc[appendix - 1].get_text()):
            failures.append("Declared appendix start has no appendix heading")
        first_text = compact(doc[0].get_text()) if total else ""
        if not all(token in first_text for token in ("队伍编号", team, "赛道", "摘要", "关键词")):
            failures.append("First page is missing the team/track table, abstract or keywords")
        if "赛道" + track not in first_text:
            failures.append("Visible track differs from compiled metadata")
        if total < 2 or "目录" not in compact(doc[1].get_text()):
            failures.append("Physical page 2 has no contents heading")
        records = []
        for i, page in enumerate(doc, 1):
            if abs(page.rect.width - 595.276) > 3 or abs(page.rect.height - 841.89) > 3:
                failures.append(f"Page {i}: expected A4 portrait paper")
            header = compact(page.get_text(clip=fitz.Rect(0, 0, page.rect.width, 40)))
            if header:
                failures.append(f"Page {i}: text appears in the reserved header band")
            text = compact(page.get_text())
            if re.search(r"REPLACE_?[A-Z_]+|MCB\d{2}XXXX|论文标题|摘要正文|这里开始论文正文", text):
                failures.append(f"Page {i}: unfilled template content")
            footer = page.get_text("words", clip=fitz.Rect(0, page.rect.height - 50, page.rect.width, page.rect.height))
            centered = [w for w in footer if abs((w[0] + w[2]) / 2 - page.rect.width / 2) <= 25]
            expected = str(i - first + 1) if i >= first else None
            number_ok = (len(centered) == 1 and centered[0][4] == expected) if expected else not footer
            if not number_ok:
                failures.append(f"Page {i}: footer should be unnumbered front matter or one centered Arabic body number")
            records.append({"page": i, "header_text_absent": not header, "footer_number_matches": number_ok})
        return {"passed": not failures, "contest_year": meta["contest_year"], "family": "mathorcup-bigdata",
                "format_rules_year": 2025, "rules_status": "provisional", "current_format_confirmation_required": True,
                "total_pages": total, "body_pages": body_pages, "max_body_pages": max_body_pages,
                "appendix_pages": total - last if appendix is not None and valid_body else 0, "pages": records,
                "pdf_sha256": file_hash(pdf_path), "metadata_sha256": file_hash(metadata_path), "failures": failures,
                "scope": "Text-layer layout, compiled boundaries and dated format baseline only; not current-rule approval, anonymity of arbitrary text/images, model validity, citations or all submission files"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--year", type=int)
    parser.add_argument("--max-body-pages", type=int, default=30)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = args.report.resolve()
        if report.exists() or report in {args.pdf.resolve(), args.metadata.resolve()}:
            raise ValueError("Use a new report path distinct from inputs")
        result = verify(args.pdf, args.metadata, args.max_body_pages, args.year)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({key: result[key] for key in ("passed", "body_pages", "appendix_pages", "rules_status", "current_format_confirmation_required", "failures")}, ensure_ascii=False))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
