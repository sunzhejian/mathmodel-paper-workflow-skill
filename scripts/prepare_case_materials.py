"""Prepare a manifest-selected original problem/data packet outside repositories.

No file discovery or reference-answer selection is performed. PDF text/PNG previews
retain all pages; formula correctness remains a human review requirement. XLSX CSVs
are lexical cell projections, with a cell ledger retaining types, formula attributes,
cached raw values and blank-cell distinctions. No formula evaluation, unit conversion,
provider call, or problem solving is performed. ZIP/XML handling uses the standard
library. PDF extraction/rendering needs an existing PyMuPDF installation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_EXPANSION_RATIO = 200
MAX_CSV_CELLS = 5_000_000
MAX_PDF_PAGES = 200
PREVIEW_DPI = 144
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".geojson", ".prj"}
RAW_SUFFIXES = {".pdf", ".xlsx", ".xls", ".doc", ".docx", ".png", ".jpg", ".jpeg",
                ".tif", ".tiff", ".webp", ".bmp", ".mat", ".npy", ".npz", ".nc",
                ".h5", ".hdf5", ".parquet", ".shp", ".shx", ".dbf", ".dat"} | TEXT_SUFFIXES
ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]*\Z")
TOP_FIELDS = {"schema_version", "case_id", "statement", "inputs", "required_roles",
              "questions", "deliverable_requirements", "expected_question_count", "required_source_ids"}
SOURCE_FIELDS = {"id", "role", "path", "label", "member", "kind", "filename_encoding"}
KINDS = {"data", "statement-supplement", "output-template"}
RESERVED_WINDOWS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                    *(f"lpt{i}" for i in range(1, 10))}


def _object(value, allowed, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: object required")
    if set(value) - allowed:
        raise ValueError(f"{where}: unknown fields: {', '.join(sorted(set(value) - allowed))}")


def _text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: nonempty text required")
    if any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f"{where}: invalid Unicode/control character")
    return value


def _identifier(value, where):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{where}: lowercase letter-led ASCII identifier required")
    return value


def _strings(value, where, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{where}: {'nonempty ' if nonempty else ''}array required")
    for item in value:
        _identifier(item, where)
    if len(set(value)) != len(value):
        raise ValueError(f"{where}: duplicate entries")
    return value


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)


def validate_manifest(spec):
    _object(spec, TOP_FIELDS, "manifest")
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("Use material contract schema_version 1")
    _identifier(spec.get("case_id"), "case_id")
    count = spec.get("expected_question_count")
    if type(count) is not int or count < 1:
        raise ValueError("expected_question_count: positive integer required")
    if not isinstance(spec.get("inputs"), list):
        raise ValueError("inputs: explicit source array required, even when empty")
    sources = [spec.get("statement"), *spec["inputs"]]
    ids = set()
    for index, item in enumerate(sources):
        _object(item, SOURCE_FIELDS, f"source[{index}]")
        ident = _identifier(item.get("id"), f"source[{index}].id")
        if ident in ids:
            raise ValueError(f"Duplicate source id: {ident}")
        ids.add(ident)
        _identifier(item.get("role"), f"{ident}.role")
        for key in ("path", "label"):
            _text(item.get(key), f"{ident}.{key}")
        if "member" in item:
            safe_member_name(_text(item["member"], f"{ident}.member"))
        if "filename_encoding" in item:
            encoding = item["filename_encoding"]
            if "member" not in item or not isinstance(encoding, str) or encoding not in {"cp437", "utf-8", "gbk", "gb18030"}:
                raise ValueError(f"{ident}: filename_encoding requires a ZIP member and an explicit supported encoding")
        if index == 0:
            if item["role"] != "statement" or item.get("kind", "statement") != "statement":
                raise ValueError("statement must explicitly declare role='statement'")
        else:
            kind = item.get("kind", "output-template" if item["role"] == "output-template" else "data")
            if not isinstance(kind, str) or kind not in KINDS:
                raise ValueError(f"{ident}: input kind must be data/statement-supplement/output-template")
            if item["role"] == "statement":
                raise ValueError("An input cannot duplicate the primary statement role")
            if item["role"] == "output-template" and kind != "output-template":
                raise ValueError("output-template role cannot be reclassified as data")
    roles = {item["role"] for item in sources}
    if "required_source_ids" in spec:
        required_ids = _strings(spec["required_source_ids"], "required_source_ids")
        if "statement" not in {item['role'] for item in sources if item['id'] in required_ids}:
            raise ValueError("required_source_ids must include the primary statement")
        if set(required_ids) - ids:
            raise ValueError("Missing required source IDs: " + ", ".join(sorted(set(required_ids) - ids)))
    required = _strings(spec.get("required_roles"), "required_roles")
    if "statement" not in required:
        raise ValueError("required_roles must include statement")
    missing = set(required) - roles
    if missing:
        raise ValueError("Missing required roles: " + ", ".join(sorted(missing)))
    questions = spec.get("questions")
    if not isinstance(questions, list) or len(questions) != count:
        raise ValueError("questions count does not match expected_question_count; declare every question")
    question_ids = set()
    for question in questions:
        _object(question, {"id", "label", "source_pages", "required_roles", "required_source_ids"}, "question")
        ident = _identifier(question.get("id"), "question.id")
        if ident in question_ids:
            raise ValueError(f"Duplicate question id: {ident}")
        question_ids.add(ident)
        _text(question.get("label"), f"{ident}.label")
        pages = question.get("source_pages")
        if (not isinstance(pages, list) or not pages or any(type(page) is not int or page < 1 for page in pages)
                or len(set(pages)) != len(pages)):
            raise ValueError(f"{ident}.source_pages: distinct one-based statement pages required")
        needed = _strings(question.get("required_roles"), f"{ident}.required_roles")
        if set(needed) - roles:
            raise ValueError(f"{ident}: missing question input roles")
        if "required_source_ids" in question:
            needed_ids = _strings(question['required_source_ids'], f"{ident}.required_source_ids")
            if set(needed_ids) - ids:
                raise ValueError(f"{ident}: missing question source IDs")
    deliverables = spec.get("deliverable_requirements")
    if not isinstance(deliverables, list) or not deliverables:
        raise ValueError("deliverable_requirements: explicitly declare question outputs")
    template_ids = {item["id"] for item in spec["inputs"]
                    if item.get("kind", "output-template" if item["role"] == "output-template" else "data") == "output-template"}
    deliverable_ids, covered, bound_templates = set(), set(), set()
    for item in deliverables:
        _object(item, {"id", "question_id", "description", "template_id"}, "deliverable")
        ident = _identifier(item.get("id"), "deliverable.id")
        if ident in deliverable_ids:
            raise ValueError(f"Duplicate deliverable id: {ident}")
        deliverable_ids.add(ident)
        if not isinstance(item.get("question_id"), str) or item["question_id"] not in question_ids:
            raise ValueError(f"{ident}: unknown question_id")
        covered.add(item["question_id"])
        _text(item.get("description"), f"{ident}.description")
        if "template_id" in item and (not isinstance(item["template_id"], str) or item["template_id"] not in template_ids):
            raise ValueError(f"{ident}: template_id must name an explicitly declared output-template source")
        if "template_id" in item:
            bound_templates.add(item['template_id'])
    if covered != question_ids:
        raise ValueError("Missing deliverable requirements for questions: " + ", ".join(sorted(question_ids - covered)))
    if bound_templates != template_ids:
        raise ValueError("Every declared output template must bind to a question deliverable: " + ", ".join(sorted(template_ids - bound_templates)))
    return sources


def safe_member_name(name):
    """Reject Windows/POSIX ambiguous members before any ZIP member is opened."""
    if not isinstance(name, str) or not name or "\\" in name or name.startswith("/"):
        raise ValueError(f"Unsafe ZIP member: {name!r}")
    trimmed = name[:-1] if name.endswith("/") else name
    parts = trimmed.split("/")
    for part in parts:
        if (part in {"", ".", ".."} or part.endswith((".", " "))
                or any(ord(c) < 32 or c in ':<>"|?*' for c in part)
                or unicodedata.normalize("NFKC", part.split(".", 1)[0]).casefold() in RESERVED_WINDOWS):
            raise ValueError(f"Unsafe ZIP member: {name!r}")
    return "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)


def validate_archive(archive):
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ValueError("ZIP has an unreasonable member count")
    names, total = {}, 0
    for info in infos:
        # ZipInfo can normalize a backslash or truncate a NUL on Windows; inspect
        # the original member spelling so that normalization cannot hide it.
        original_name = getattr(info, "orig_filename", info.filename)
        safe_member_name(original_name)
        # Some configured Windows ZIP readers decode legacy Chinese names after
        # ZipInfo construction. Permit safe spelling changes, while validating
        # both forms; an original backslash/NUL/traversal can never be hidden.
        key = safe_member_name(info.filename)
        if key in names:
            raise ValueError(f"Duplicate/casefold-conflicting ZIP members: {names[key]} / {info.filename}")
        names[key] = info.filename
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError(f"ZIP symlink/special member refused: {info.filename}")
        if info.flag_bits & 1:
            raise ValueError(f"Encrypted ZIP member refused: {info.filename}")
        if info.file_size > MAX_MEMBER_BYTES or info.compress_size > MAX_ARCHIVE_BYTES:
            raise ValueError(f"ZIP member size is unreasonable: {info.filename}")
        if info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > MAX_EXPANSION_RATIO:
            raise ValueError(f"ZIP expansion ratio is unreasonable: {info.filename}")
        total += info.file_size
        if total > MAX_ARCHIVE_BYTES:
            raise ValueError("ZIP total uncompressed size is unreasonable")
    # A file named A cannot also be the implicit parent of A/b, even if the
    # archive omitted a corresponding directory entry.
    files = {safe_member_name(info.filename) for info in infos if not info.is_dir()}
    for key in names:
        parts = key.split("/")
        if any("/".join(parts[:n]) in files for n in range(1, len(parts))):
            raise ValueError("ZIP file/directory ancestor conflict")
    return {info.filename: info for info in infos}


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_source(item, manifest_dir, cache):
    path = (manifest_dir / item["path"]).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError(f"{item['id']}: source is not a bounded file")
    if "member" in item:
        if path.suffix.casefold() != ".zip":
            raise ValueError(f"{item['id']}: member selection requires a ZIP source")
        cache_key = (path, item.get("filename_encoding"))
        if cache_key not in cache:
            zip_data = path.read_bytes()
            archive = zipfile.ZipFile(io.BytesIO(zip_data), metadata_encoding=item.get("filename_encoding"))
            cache[cache_key] = (archive, validate_archive(archive), _sha_bytes(zip_data))
        archive, infos, archive_hash = cache[cache_key]
        member = item["member"]
        if member not in infos or infos[member].is_dir():
            raise ValueError(f"{item['id']}: exact fixed member is missing or is a directory")
        with archive.open(infos[member]) as stream:
            data = stream.read(MAX_MEMBER_BYTES + 1)
        if len(data) > MAX_MEMBER_BYTES:
            raise ValueError("Selected member exceeds material size limit")
        name = PurePosixPath(member).name
        provenance = {"source_path": str(path), "member": member, "archive_sha256": archive_hash}
        if "filename_encoding" in item:
            provenance["filename_encoding"] = item["filename_encoding"]
        if getattr(infos[member], "orig_filename", member) != member:
            provenance["filename_decoding_note"] = "ZIP reader exposes a different decoded name than orig_filename; both spellings passed path-safety checks."
    else:
        if path.suffix.casefold() == ".zip":
            raise ValueError(f"{item['id']}: ZIP sources require an explicit fixed member; no extract-all mode")
        if path.stat().st_size > MAX_MEMBER_BYTES:
            raise ValueError(f"{item['id']}: selected source exceeds material size limit")
        data, name = path.read_bytes(), path.name
        provenance = {"source_path": str(path)}
    safe_member_name(name)
    suffix = Path(name).suffix.casefold()
    if suffix not in RAW_SUFFIXES:
        raise ValueError(f"{item['id']}: unsupported original-material type; executable scripts/programs are not case inputs")
    kind = item.get("kind", "output-template" if item["role"] == "output-template" else "data")
    if item["role"] == "statement":
        kind = "statement"
    if kind == "statement" and suffix != ".pdf":
        raise ValueError(f"{item['id']}: the primary statement must be PDF")
    if kind == "output-template" and suffix != ".xlsx":
        raise ValueError(f"{item['id']}: this output-template adapter requires XLSX")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError(f"{item['id']}: invalid PDF header")
    return {"source": item, "name": name, "suffix": suffix, "kind": kind,
            "bytes": data, "sha256": _sha_bytes(data), "provenance": provenance}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _xml(data, where):
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError(f"{where}: DTD/entity XML is unsupported")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"{where}: invalid XML") from exc


def _children(parent, tag):
    return [node for node in parent if _local(node.tag) == tag]


def _one(parent, tag):
    items = _children(parent, tag)
    if len(items) > 1:
        raise ValueError(f"Duplicate {tag} element in XLSX")
    return items[0] if items else None


def _rich_text(parent):
    if parent is None:
        return ""
    # Phonetic annotations (rPh) are not a second copy of the cell text.
    chunks = []
    for child in parent:
        if _local(child.tag) == "t":
            chunks.append(child.text or "")
        elif _local(child.tag) == "r":
            chunks.extend(node.text or "" for node in child if _local(node.tag) == "t")
    return "".join(chunks)


def _address(value):
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]*)", value or "")
    if not match:
        raise ValueError(f"XLSX cell needs an explicit address: {value!r}")
    column = 0
    for char in match[1].upper():
        column = column * 26 + ord(char) - ord("A") + 1
    row = int(match[2])
    if column > 16384 or row > 1048576:
        raise ValueError("XLSX cell is outside standard worksheet coordinates")
    return row, column


def _dimension(value):
    if value is None:
        return 0, 0
    if not isinstance(value, str) or len(value.split(":")) > 2:
        raise ValueError("Invalid raw worksheet dimension")
    start = _address(value.split(":")[0])
    end = _address(value.split(":")[-1])
    if end[0] < start[0] or end[1] < start[1]:
        raise ValueError("Reversed raw worksheet dimension")
    return end


def inspect_xlsx(data):
    """Read every worksheet without interpreting formats or evaluating formulas."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = validate_archive(archive)
        if "xl/workbook.xml" not in infos or "xl/_rels/workbook.xml.rels" not in infos:
            raise ValueError("XLSX workbook and sheet relationships are required")
        workbook = _xml(archive.read("xl/workbook.xml"), "workbook")
        relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"), "workbook relationships")
        if _local(workbook.tag) != "workbook" or _local(relationships.tag) != "Relationships":
            raise ValueError("XLSX package members have unexpected root elements")
        relations = {}
        for relation in relationships:
            if _local(relation.tag) != "Relationship":
                continue
            ident = relation.attrib.get("Id")
            if not ident or ident in relations:
                raise ValueError("Duplicate/missing XLSX relationship Id")
            relations[ident] = relation.attrib
        shared = []
        if "xl/sharedStrings.xml" in infos:
            strings = _xml(archive.read("xl/sharedStrings.xml"), "shared strings")
            shared = [_rich_text(item) for item in strings if _local(item.tag) == "si"]
        sheets_node = _one(workbook, "sheets")
        if sheets_node is None:
            raise ValueError("XLSX has no sheet inventory")
        sheet_names, sheets = set(), []
        for declaration in _children(sheets_node, "sheet"):
            name = declaration.attrib.get("name")
            if not name or name.casefold() in sheet_names:
                raise ValueError("XLSX duplicate/missing sheet name")
            sheet_names.add(name.casefold())
            rid = next((value for key, value in declaration.attrib.items() if _local(key) == "id"), None)
            relation = relations.get(rid)
            if not relation or relation.get("TargetMode", "Internal") != "Internal":
                raise ValueError(f"{name}: missing/external sheet relationship")
            if not relation.get("Type", "").rstrip("/").endswith("/worksheet"):
                raise ValueError(f"{name}: non-worksheet tabs require a separate adapter; original workbook retained")
            target = relation.get("Target", "")
            target = target[1:] if target.startswith("/") else posixpath.join("xl", target)
            target = posixpath.normpath(target)
            if not target.startswith("xl/") or target not in infos or infos[target].is_dir():
                raise ValueError(f"{name}: worksheet target is missing or escapes the workbook")
            worksheet = _xml(archive.read(target), f"sheet {name}")
            if _local(worksheet.tag) != "worksheet":
                raise ValueError(f"{name}: declared worksheet has a different XML root")
            raw_dimension_node = _one(worksheet, "dimension")
            raw_dimension = raw_dimension_node.attrib.get("ref") if raw_dimension_node is not None else None
            max_row, max_col = _dimension(raw_dimension)
            cells, grid = [], {}
            sheet_data = _one(worksheet, "sheetData")
            if sheet_data is not None:
                for row_node in _children(sheet_data, "row"):
                    for cell in _children(row_node, "c"):
                        address = cell.attrib.get("r")
                        row, col = _address(address)
                        if (row, col) in grid:
                            raise ValueError(f"{name}: duplicate cell address {address}")
                        if "r" in row_node.attrib and row_node.attrib["r"] != str(row):
                            raise ValueError(f"{name}: row index disagrees with cell {address}")
                        kind = cell.attrib.get("t", "n")
                        value_node, formula = _one(cell, "v"), _one(cell, "f")
                        raw_value = value_node.text if value_node is not None else None
                        if formula is not None:
                            projected = "=" + (formula.text or "")
                        elif kind == "s":
                            try:
                                index = int(raw_value)
                            except (ValueError, TypeError) as exc:
                                raise ValueError(f"{name}/{address}: invalid shared string index") from exc
                            if index < 0 or index >= len(shared):
                                raise ValueError(f"{name}/{address}: missing shared string")
                            projected = shared[index]
                        elif kind == "inlineStr":
                            projected = _rich_text(_one(cell, "is"))
                        elif kind in {"n", "b", "e", "str", "d"}:
                            projected = raw_value or ""
                        else:
                            raise ValueError(f"{name}/{address}: unsupported stored cell type {kind!r}")
                        record = {"address": address, "row": row, "column": col,
                                  "cell_attributes": dict(cell.attrib), "stored_type": kind,
                                  "stored_value_lexical": raw_value, "csv_value": projected,
                                  "formula": None if formula is None else {"text": formula.text or "",
                                                                           "attributes": dict(formula.attrib)},
                                  "cached_value_used": False}
                        cells.append(record)
                        grid[row, col] = projected
                        max_row, max_col = max(max_row, row), max(max_col, col)
            if max_row * max_col > MAX_CSV_CELLS:
                raise ValueError(f"{name}: full declared rectangle exceeds CSV cell limit; no truncation is performed")
            formulas = [cell for cell in cells if cell["formula"] is not None]
            nonempty_rows = sorted({row for (row, _), value in grid.items() if value != ""})
            warnings = []
            declared_row, declared_col = _dimension(raw_dimension)
            if raw_dimension and (max_row > declared_row or max_col > declared_col):
                warnings.append("Stored cells exceed raw dimension; CSV includes all declared and stored coordinates.")
            if any(not cell["formula"]["text"] for cell in formulas):
                warnings.append("Formula elements with no expression text are retained as '='; shared/array formulas are not reconstructed or evaluated.")
            sheets.append({"name": name, "state": declaration.attrib.get("state", "visible"),
                           "sheet_id": declaration.attrib.get("sheetId"), "worksheet_member": target,
                           "raw_dimension": raw_dimension, "csv_origin": "A1", "csv_rows": max_row,
                           "csv_columns": max_col, "stored_cell_count": len(cells),
                           "nonempty_rows": nonempty_rows, "nonempty_row_count": len(nonempty_rows),
                           "formula_cell_count": len(formulas), "formula_cells": formulas,
                           "warnings": warnings, "cells": cells, "grid": grid})
        if not sheets:
            raise ValueError("XLSX has no worksheets")
        return sheets


def _write_xlsx_exports(sheets, directory):
    directory.mkdir(parents=True)
    reports = []
    for index, sheet in enumerate(sheets, 1):
        name = f"sheet-{index:03d}"
        csv_path = directory / (name + ".csv")
        # No invented header: row 1 and every empty position are source positions.
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            for row in range(1, sheet["csv_rows"] + 1):
                writer.writerow([sheet["grid"].get((row, col), "") for col in range(1, sheet["csv_columns"] + 1)])
        ledger_path = directory / (name + "-cells.json")
        ledger_path.write_text(json.dumps(sheet["cells"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = {key: value for key, value in sheet.items() if key not in {"grid", "cells"}}
        report.update({"csv": csv_path.name, "cell_ledger": ledger_path.name,
                       "csv_sha256": _sha_bytes(csv_path.read_bytes())})
        reports.append(report)
    return reports


def _pdf_exports(data, directory):
    directory.mkdir(parents=True)
    try:
        import pymupdf
    except ImportError:
        return {"status": "unavailable", "page_count": None, "pages": [],
                "limitation": "PyMuPDF is unavailable; original PDF retained, no text/page preview claimed."}
    pages, all_text = [], []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if document.is_encrypted or not 1 <= len(document) <= MAX_PDF_PAGES:
            raise ValueError("Encrypted PDF or unreasonable page count")
        text_failures = []
        for index, page in enumerate(document, 1):
            if page.rect.width * page.rect.height * (PREVIEW_DPI / 72) ** 2 > 20_000_000:
                raise ValueError("PDF page preview would exceed a reasonable pixel budget; original retained")
            text_path = directory / f"page-{index:03d}.txt"
            image_path = directory / f"page-{index:03d}.png"
            # Save the authoritative page render even when extraction fails or
            # cannot reconstruct mathematical expressions faithfully.
            page.get_pixmap(dpi=PREVIEW_DPI, alpha=False).save(image_path)
            text_error = None
            try:
                text = page.get_text("text", sort=False)
            except Exception as exc:
                text, text_error = "", str(exc)
                text_failures.append(index)
            text_path.write_text(text, encoding="utf-8")
            all_text.append(f"\n--- PAGE {index} ---\n" + text)
            pages.append({"page": index, "text": text_path.name, "png": image_path.name,
                          "text_characters": len(text), "preview_dpi": PREVIEW_DPI,
                          "text_sha256": _sha_bytes(text_path.read_bytes()),
                          "png_sha256": _sha_bytes(image_path.read_bytes()),
                          "text_extraction_error": text_error,
                          "text_review_required": True,
                          "formula_transcription_status": "not verified; inspect the original PDF and page image"})
        (directory / "full-text.txt").write_text("".join(all_text), encoding="utf-8")
        incomplete = bool(text_failures) or any(page["text_characters"] < 20 for page in pages)
        return {"status": "extracted_with_limitations" if incomplete else "extracted",
                "page_count": len(document), "pages": pages,
                "full_text": "full-text.txt", "text_order": "renderer extraction order, not corrected reading order",
                "formula_transcription_status": "unverified", "ocr_performed": False,
                "warnings": ["Text extraction failed or is sparse/empty on one or more pages; original page images remain authoritative."]
                            if incomplete else [],
                "limitation": "Some page text cannot be fully extracted; use retained original PDFs and page images and verify formulas manually."
                              if incomplete else None}


def _check_output_location(output):
    if output.exists():
        raise ValueError("Output must be a NEW directory; existing materials are never overwritten")
    skill_root = Path(__file__).resolve().parents[1]
    if output.is_relative_to(skill_root):
        raise ValueError("Original case materials must stay outside the public skill/project directory")
    for directory in (output, *output.parents):
        if (directory / ".git").exists():
            raise ValueError("Original case materials must stay outside Git repositories; choose an independent research directory")


def prepare(manifest, output):
    manifest, output = Path(manifest).resolve(strict=True), Path(output).resolve()
    _check_output_location(output)
    spec = read_manifest(manifest)
    sources = validate_manifest(spec)
    cache, selected = {}, []
    try:
        for source in sources:
            selected.append(_read_source(source, manifest.parent, cache))
    finally:
        for archive, _, _ in cache.values():
            archive.close()
    # Validate all XLSX cells before making the destination; failures cannot yield
    # silently partial CSVs or overwrite a user's workbook.
    for item in selected:
        if item["suffix"] == ".xlsx":
            item["sheets"] = inspect_xlsx(item["bytes"])
    output.mkdir(parents=True, exist_ok=False)
    (output / "material_contract.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files, limitations = [], []
    try:
        for item in selected:
            source = item["source"]
            relative = Path("raw") / source["id"] / item["name"]
            raw_path = output / relative
            raw_path.parent.mkdir(parents=True)
            raw_path.write_bytes(item["bytes"])
            if _sha_bytes(raw_path.read_bytes()) != item["sha256"]:
                raise OSError("Raw byte/hash preservation failed")
            receipt = {"id": source["id"], "role": source["role"], "kind": item["kind"],
                       "label": source["label"], "raw_path": relative.as_posix(),
                       "bytes": len(item["bytes"]), "sha256": item["sha256"], **item["provenance"],
                       "review_required": True,
                       "reference_answer_status": "not inspected automatically; original-input status is a host manifest declaration",
                       "interpretation": "output schema/layout only; not a reference answer" if item["kind"] == "output-template"
                                         else "manifest-declared original input; source/content fidelity needs review"}
            if item["suffix"] == ".xlsx":
                exports = Path("spreadsheets") / source["id"]
                receipt.update({"exports_directory": exports.as_posix(),
                                "worksheets": _write_xlsx_exports(item["sheets"], output / exports),
                                "projection_scope": "lexical cell strings/formula source text plus typed cell ledger; formatting, formulas and units are not interpreted",
                                "formula_evaluation_performed": False, "unit_conversion_performed": False})
            elif item["suffix"] == ".pdf":
                exports = Path("pdf") / source["id"]
                receipt.update({"exports_directory": exports.as_posix(),
                                "pdf": _pdf_exports(item["bytes"], output / exports)})
                if receipt["pdf"]["status"] != "extracted":
                    limitations.append(receipt["pdf"]["limitation"])
            elif item["suffix"] in TEXT_SUFFIXES:
                try:
                    text = item["bytes"].decode("utf-8-sig")
                except UnicodeDecodeError:
                    receipt["content_extraction"] = {"status": "not-covered", "original_preserved": True,
                        "reason": "Text is not strict UTF-8; encoding is not guessed or converted."}
                    limitations.append(f"{source['id']}: non-UTF-8 text retained as raw original; readable decoding needs review.")
                else:
                    readable = Path("readable") / (source["id"] + item["suffix"])
                    (output / readable).parent.mkdir(parents=True, exist_ok=True)
                    (output / readable).write_text(text, encoding="utf-8", newline="")
                    receipt["content_extraction"] = {"status": "utf8-readable-copy", "path": readable.as_posix(),
                        "characters": len(text), "encoding": "utf-8", "bom_removed_in_readable_copy": item["bytes"].startswith(b"\xef\xbb\xbf"),
                        "original_bytes_unchanged": True,
                        "scope": "complete Unicode text; no CSV value conversion, Markdown instruction execution or semantic parsing"}
            else:
                receipt["content_extraction"] = {"status": "not-covered", "original_preserved": True,
                    "reason": "Only raw bytes/hash are retained for this supplementary format; content was not parsed or executed."}
                limitations.append(f"{source['id']}: {item['suffix']} content parsing is not covered; review the retained original.")
            files.append(receipt)
        statement = next(item for item in files if item["kind"] == "statement")
        page_count = statement["pdf"]["page_count"]
        if page_count is not None:
            for question in spec["questions"]:
                if max(question["source_pages"]) > page_count:
                    raise ValueError(f"{question['id']}: question source page exceeds complete original PDF")
        else:
            limitations.append("Question-to-page bindings could not be checked without a PDF page inventory.")
        completeness = {"required_roles_present": True, "declared_question_count_matches": True,
                        "required_source_ids_checked": "required_source_ids" in spec,
                        "all_declared_output_templates_bound": True,
                        "all_declared_sources_copied": len(files) == len(sources),
                        "question_source_pages_checked": page_count is not None,
                        "questions": spec["questions"], "deliverable_requirements": spec["deliverable_requirements"],
                        "semantic_completeness": "not established by existence, hashes, page count or declared roles",
                        "review_required": True}
        report = {"schema_version": 1, "case_id": spec["case_id"],
                  "status": "prepared_with_limitations" if limitations else "prepared",
                  "manifest_sha256": _sha_bytes(manifest.read_bytes()),
                  "files": files, "output_templates": [item["id"] for item in files if item["kind"] == "output-template"],
                  "completeness": completeness, "limitations": limitations, "review_required": True,
                  "scientific_semantics_verified": False, "solver_executed": False,
                  "capabilities": {"material_copy": True,
                                   "pdf_page_previews": all(item["pdf"]["page_count"] is not None and len(item["pdf"]["pages"]) == item["pdf"]["page_count"] for item in files if "pdf" in item),
                                   "pdf_text_extraction": all(item["pdf"]["status"] == "extracted" for item in files if "pdf" in item),
                                   "xlsx_cell_projection": True, "formula_evaluation": False,
                                   "complete_problem_solving": False, "provider_called": False},
                  "handoff": "Give the recipient the complete raw statement, every declared original input and output-template, the contract, all page previews/texts and file_manifest.json. Require independent checks of formulas, all questions, annexes, units and template layout before solving."}
    except Exception as exc:
        failure = {"case_id": spec["case_id"], "status": "preparation_failed", "error": str(exc),
                   "files": files, "review_required": True,
                   "handoff_ready": False, "original_inputs_retained": True}
        (output / "file_manifest.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    (output / "file_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Explicit original-material whitelist JSON")
    parser.add_argument("--output", required=True, type=Path, help="NEW independent research directory outside repositories")
    args = parser.parse_args()
    try:
        report = prepare(args.manifest, args.output)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "files": len(report["files"]), "review_required": True}, ensure_ascii=False))
    return 0 if report["status"] == "prepared" else 2


if __name__ == "__main__":
    raise SystemExit(main())
