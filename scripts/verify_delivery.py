"""Verify that a PDF audit, preserved appendix, and support ZIP belong to one delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

import pymupdf as fitz


def digest(stream) -> str:
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return digest(stream)


def check_support(archive_path: Path, support_root: Path | None) -> tuple[int, list[str]]:
    failures: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            failures.append("Support ZIP contains duplicate names")
        if "MANIFEST.json" not in names:
            return 0, failures + ["Support ZIP has no MANIFEST.json"]
        manifest = json.loads(archive.read("MANIFEST.json").decode("utf-8"))
        records = manifest.get("files")
        if not isinstance(records, list) or not records:
            raise ValueError("Support manifest needs a nonempty files array")
        listed: set[str] = set()
        for item in records:
            name = item.get("path")
            if not isinstance(name, str) or not isinstance(item.get("sha256"), str) or not isinstance(item.get("size"), int):
                raise ValueError("Malformed support manifest record")
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ":" in name or name == "MANIFEST.json":
                raise ValueError(f"Unsafe support manifest path: {name}")
            if name in listed:
                failures.append(f"Support manifest repeats {name}")
            listed.add(name)
            if name not in names:
                failures.append(f"Support ZIP is missing {name}")
                continue
            with archive.open(name) as stream:
                content_hash = digest(stream)
            if content_hash != item["sha256"] or archive.getinfo(name).file_size != item["size"]:
                failures.append(f"Support ZIP content differs from manifest: {name}")
            if support_root is not None:
                file = (support_root / Path(*relative.parts)).resolve()
                if not file.is_relative_to(support_root) or not file.is_file() or file_hash(file) != item["sha256"]:
                    failures.append(f"Support source differs from ZIP: {name}")
        if set(names) != listed | {"MANIFEST.json"}:
            failures.append("Support ZIP entries differ from manifest")
        return len(records), failures


def verify(body: Path, original: Path, final: Path, layout_report: Path,
           appendix_report: Path, support_zip: Path | None = None,
           support_root: Path | None = None) -> dict:
    body, original, final = (path.resolve(strict=True) for path in (body, original, final))
    layout = json.loads(layout_report.read_text(encoding="utf-8-sig"))
    appendix = json.loads(appendix_report.read_text(encoding="utf-8-sig"))
    failures: list[str] = []
    hashes = {"body": file_hash(body), "original": file_hash(original), "final": file_hash(final)}
    for label, actual, expected in [
        ("body audit", hashes["body"], layout.get("pdf_sha256")),
        ("appendix input body", hashes["body"], appendix.get("body_sha256")),
        ("appendix source", hashes["original"], appendix.get("source_sha256")),
        ("final PDF", hashes["final"], appendix.get("output_sha256")),
    ]:
        if actual != expected:
            failures.append(f"{label} hash is stale or mismatched")
    if layout.get("passed") is not True or layout.get("failures"):
        failures.append("Body PDF audit did not pass")
    with fitz.open(body) as document:
        body_pages = len(document)
    with fitz.open(final) as document:
        total_pages = len(document)
    if layout.get("selected_pages") != body_pages or layout.get("total_pages") != body_pages:
        failures.append("Body audit does not cover the entire delivered body PDF")
    if appendix.get("body_pages") != body_pages or appendix.get("total_pages") != total_pages:
        failures.append("Appendix report page counts differ from delivered PDFs")
    appendix_pages = appendix.get("appendix_pages")
    if not isinstance(appendix_pages, int) or appendix_pages < 1 or total_pages != body_pages + appendix_pages:
        failures.append("Final PDF does not contain the reported appendix page count")
    if appendix.get("appendix_pages_verified") != appendix_pages:
        failures.append("Appendix preservation verification is incomplete")
    if appendix.get("numbered_appendix") and appendix.get("appendix_number_range") != [body_pages + 1, total_pages]:
        failures.append("Reported appendix page number range is not continuous")
    support_count = None
    if support_root is not None and support_zip is None:
        raise ValueError("--support-root requires --support-zip")
    if support_zip is not None:
        support_count, support_failures = check_support(
            support_zip.resolve(strict=True), support_root.resolve(strict=True) if support_root else None)
        failures.extend(support_failures)
    return {"passed": not failures, "body_pages": body_pages, "total_pages": total_pages,
            "appendix_pages": appendix_pages, "support_files_checked": support_count,
            "hashes": hashes, "failures": failures,
            "scope": "File and report consistency; not semantic model, citation, or visual-layout review"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path)
    parser.add_argument("original_appendix_source", type=Path)
    parser.add_argument("final", type=Path)
    parser.add_argument("layout_report", type=Path)
    parser.add_argument("appendix_report", type=Path)
    parser.add_argument("--support-zip", type=Path)
    parser.add_argument("--support-root", type=Path)
    parser.add_argument("--report", type=Path, help="New JSON report path; existing files are preserved")
    args = parser.parse_args()
    try:
        result = verify(args.body, args.original_appendix_source, args.final,
                        args.layout_report, args.appendix_report,
                        args.support_zip, args.support_root)
        if args.report:
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
