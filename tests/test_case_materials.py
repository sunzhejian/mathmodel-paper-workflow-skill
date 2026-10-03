"""Synthetic fixtures only: original competition files never enter public tests."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

try:
    import pymupdf
except ImportError:
    pymupdf = None

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case_materials", ROOT / "scripts/prepare_case_materials.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def synthetic_xlsx():
    """Two worksheets: all major lexical cell types and shared formula metadata."""
    workbook = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Raw cells" sheetId="1" r:id="rId1"/>'
                '<sheet name="Empty template" sheetId="2" state="hidden" r:id="rId2"/></sheets></workbook>')
    relationships = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                     '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="/xl/worksheets/sheet2.xml"/>'
                     '</Relationships>')
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<dimension ref="A1:D4"/><sheetData>'
             '<row r="1"><c r="A1" t="inlineStr"><is><t>Time (s)</t></is></c>'
             '<c r="B1" t="inlineStr"><is><t>Original unit</t></is></c></row>'
             '<row r="2"><c r="A2"><v>1.0000</v></c>'
             '<c r="B2" t="inlineStr"><is><t xml:space="preserve">  keep spaces  </t></is></c>'
             '<c r="C2" t="s"><v>0</v></c><c r="D2"><f>SUM(A2:A4)</f><v>999</v></c></row>'
             '<row r="3"><c r="A3" s="2"/><c r="C3" t="e"><v>#N/A</v></c><c r="D3" t="b"><v>1</v></c></row>'
             '<row r="4"><c r="A4"><v>003.140000</v></c><c r="B4" s="1"><v>45000</v></c>'
             '<c r="D4"><f t="shared" si="0" ref="D4:D5">A4*2</f><v>6.28</v></c></row>'
             '<row r="5"><c r="D5"><f t="shared" si="0"/><v>8</v></c></row>'
             '</sheetData></worksheet>')
    shared = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<si><r><t>alpha</t></r><r><t xml:space="preserve">  beta</t></r>'
              '<rPh sb="0" eb="1"><t>phonetic-not-cell-value</t></rPh></si></sst>')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/worksheets/sheet2.xml", '<worksheet><dimension ref="A1:B3"/><sheetData/></worksheet>')
        archive.writestr("xl/sharedStrings.xml", shared)
    return stream.getvalue()


def synthetic_pdf():
    with pymupdf.open() as document:
        for i in range(1, 5):
            page = document.new_page(width=200, height=240)
            page.insert_text((15, 35), f"Synthetic original problem page {i}", fontsize=8)
            page.insert_text((15, 60), f"Question {i}: retain source equations and units.", fontsize=8)
        return document.tobytes()


def manifest():
    return {
        "schema_version": 1, "case_id": "synthetic-four-question-case", "expected_question_count": 4,
        "statement": {"id": "statement", "role": "statement", "path": "originals.zip", "member": "problem.pdf", "label": "Entire original problem"},
        "inputs": [
            {"id": "data", "role": "measurements", "path": "originals.zip", "member": "input/raw.xlsx", "label": "Original observations"},
            {"id": "template", "role": "output-template", "path": "originals.zip", "member": "output/result.xlsx", "label": "Original empty output layout"},
        ],
        "required_roles": ["statement", "measurements", "output-template"],
        "questions": [{"id": f"q{i}", "label": f"Question {i}", "source_pages": [i],
                       "required_roles": ["statement", "measurements"]} for i in range(1, 5)],
        "deliverable_requirements": [{"id": f"deliverable-{i}", "question_id": f"q{i}",
                                     "description": "Fill the declared result layout from a reproducible independent solver.",
                                     "template_id": "template"} for i in range(1, 5)],
    }


def originals(folder):
    path = folder / "originals.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("problem.pdf", synthetic_pdf())
        archive.writestr("input/raw.xlsx", synthetic_xlsx())
        archive.writestr("output/result.xlsx", synthetic_xlsx())
        # Explicitly excluded; the adapter must not copy archive extras.
        archive.writestr("old-paper.pdf", b"not-an-authorized-statement")
        archive.writestr("old-solver.py", b"print('must not be an input')")
    contract = folder / "materials.json"
    contract.write_text(json.dumps(manifest()), encoding="utf-8")
    return path, contract


class CaseMaterialsTests(unittest.TestCase):
    def test_every_sheet_preserves_lexical_cells_formulas_blanks_and_hidden_state(self):
        sheets = m.inspect_xlsx(synthetic_xlsx())
        self.assertEqual(len(sheets), 2)
        first, empty = sheets
        self.assertEqual(first["raw_dimension"], "A1:D4")
        self.assertEqual((first["csv_rows"], first["csv_columns"]), (5, 4))
        self.assertEqual(first["grid"][2, 1], "1.0000")
        self.assertEqual(first["grid"][2, 2], "  keep spaces  ")
        self.assertEqual(first["grid"][2, 3], "alpha  beta")
        self.assertEqual(first["grid"][2, 4], "=SUM(A2:A4)")
        self.assertEqual(first["grid"][4, 1], "003.140000")
        self.assertEqual(first["grid"][4, 2], "45000", "date serial must not be interpreted")
        self.assertEqual(first["grid"][5, 4], "=")
        self.assertEqual(first["grid"][3, 1], "")
        self.assertNotIn((3, 2), first["grid"], "absent and present-blank cells stay distinguishable in the ledger")
        self.assertEqual(first["formula_cell_count"], 3)
        self.assertEqual(first["formula_cells"][0]["stored_value_lexical"], "999")
        self.assertFalse(first["formula_cells"][0]["cached_value_used"])
        self.assertEqual(empty["state"], "hidden")
        self.assertEqual(empty["raw_dimension"], "A1:B3")
        self.assertEqual(empty["nonempty_rows"], [])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "cells"
            m._write_xlsx_exports(sheets, output)
            with (output / "sheet-001.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(len(row) == 4 for row in rows))
            self.assertEqual(rows[0], ["Time (s)", "Original unit", "", ""])
            self.assertEqual(rows[1][3], "=SUM(A2:A4)")
            with (output / "sheet-002.csv").open(encoding="utf-8", newline="") as stream:
                self.assertEqual(list(csv.reader(stream)), [["", ""]] * 3)

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_full_packet_preserves_only_selected_bytes_all_pages_and_template_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            archive, contract = originals(base)
            before = archive.read_bytes()
            output = base / "independent-research"
            report = m.prepare(contract, output)
            self.assertEqual(report["status"], "prepared")
            self.assertEqual(len(report["files"]), 3)
            self.assertTrue(report["review_required"])
            self.assertFalse(report["scientific_semantics_verified"])
            self.assertFalse(report["solver_executed"])
            self.assertFalse(report["capabilities"]["complete_problem_solving"])
            self.assertEqual(report["output_templates"], ["template"])
            with zipfile.ZipFile(io.BytesIO(before)) as source:
                for item in report["files"]:
                    copied = (output / item["raw_path"]).read_bytes()
                    self.assertEqual(copied, source.read(item["member"]))
                    self.assertEqual(hashlib.sha256(copied).hexdigest(), item["sha256"])
                    self.assertIn('not inspected automatically',item['reference_answer_status'])
            names = {path.name for path in output.rglob("*") if path.is_file()}
            self.assertNotIn("old-paper.pdf", names)
            self.assertNotIn("old-solver.py", names)
            primary = next(item for item in report["files"] if item["role"] == "statement")
            self.assertEqual(primary["pdf"]["page_count"], 4)
            self.assertEqual(len(primary["pdf"]["pages"]), 4)
            for page in primary["pdf"]["pages"]:
                path = output / primary["exports_directory"] / page["png"]
                self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertIn("Synthetic original problem", (path.parent / page["text"]).read_text(encoding="utf-8"))
                self.assertIn("not verified", page["formula_transcription_status"])
            self.assertEqual(archive.read_bytes(), before)

    def test_declared_four_questions_cannot_be_reduced_or_duplicated(self):
        contract = manifest()
        contract["questions"].pop()
        with self.assertRaisesRegex(ValueError, "count does not match"):
            m.validate_manifest(contract)
        contract = manifest()
        contract["questions"][3]["id"] = "q1"
        with self.assertRaisesRegex(ValueError, "Duplicate question"):
            m.validate_manifest(contract)

    def test_missing_role_or_question_output_requirement_is_rejected(self):
        contract = manifest()
        contract["required_roles"].append("missing-attachment")
        with self.assertRaisesRegex(ValueError, "Missing required roles"):
            m.validate_manifest(contract)
        contract = manifest()
        contract["deliverable_requirements"].pop()
        with self.assertRaisesRegex(ValueError, "Missing deliverable requirements"):
            m.validate_manifest(contract)

    def test_data_cannot_be_bound_as_an_output_template(self):
        contract = manifest()
        contract["deliverable_requirements"][0]["template_id"] = "data"
        with self.assertRaisesRegex(ValueError, "output-template"):
            m.validate_manifest(contract)
        contract = manifest()
        contract["inputs"][1]["kind"] = "data"
        with self.assertRaisesRegex(ValueError, "cannot be reclassified"):
            m.validate_manifest(contract)

    def test_declared_template_cannot_be_silently_unbound(self):
        contract = manifest()
        for item in contract['deliverable_requirements']:
            item.pop('template_id')
        with self.assertRaisesRegex(ValueError, 'Every declared output template'):
            m.validate_manifest(contract)

    def test_source_ids_detect_missing_file_even_when_role_still_exists(self):
        contract = manifest()
        second = dict(contract['inputs'][0], id='second-measurements')
        contract['inputs'].append(second)
        contract['required_source_ids']=['statement','data','second-measurements','template']
        m.validate_manifest(contract)
        contract['inputs'].pop()
        with self.assertRaisesRegex(ValueError, 'Missing required source IDs'):
            m.validate_manifest(contract)

    def test_question_specific_source_id_cannot_be_missing_or_empty(self):
        for required_ids in (['unlisted-measurements'], []):
            with self.subTest(required_ids=required_ids):
                contract=manifest()
                contract['questions'][0]['required_source_ids']=required_ids
                with self.assertRaisesRegex(ValueError, 'missing question source IDs|nonempty'):
                    m.validate_manifest(contract)

    def test_unknown_or_duplicate_contract_fields_are_rejected(self):
        contract = manifest()
        contract["auto_find_answers"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            m.validate_manifest(contract)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
                m.read_manifest(path)

    def test_unsafe_zip_paths_are_rejected_even_when_not_selected(self):
        for name in ("../escape.xlsx", "/absolute.xlsx", "C:/absolute.xlsx", "safe\\evil.xlsx",
                     "a/../x.xlsx", "a//x.xlsx", "a./x.xlsx", "CON.xlsx", "COM¹.xlsx", "x.xlsx:stream"):
            with self.subTest(name=name):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr("allowed.xlsx", b"allowed")
                    archive.writestr(name, b"unselected malicious entry")
                data = stream.getvalue()
                if "\\" in name:
                    # Windows ZipInfo normalizes backslashes at fixture creation;
                    # put the actual untrusted spelling into both ZIP headers.
                    data = data.replace(name.replace("\\", "/").encode(), name.encode())
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
                        m.validate_archive(archive)

    def test_zip_casefold_duplicates_symlinks_and_file_parent_conflicts_are_rejected(self):
        for entries in (("Data.xlsx", "data.xlsx"), ("data.xlsx", "data.xlsx"), ("parent", "parent/child.xlsx")):
            stream = io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(stream, "w") as archive:
                    for entry in entries:
                        archive.writestr(entry, b"fixture")
            with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
                with self.assertRaises(ValueError):
                    m.validate_archive(archive)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo("link.xlsx")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../outside.xlsx")
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.validate_archive(archive)

    def test_encrypted_and_unreasonable_member_metadata_are_rejected(self):
        class MetadataArchive:
            def __init__(self, info): self.info = info
            def infolist(self): return [self.info]
        info = zipfile.ZipInfo("a.xlsx")
        info.flag_bits = 1
        with self.assertRaisesRegex(ValueError, "Encrypted"):
            m.validate_archive(MetadataArchive(info))
        info.flag_bits = 0
        info.file_size = m.MAX_MEMBER_BYTES + 1
        with self.assertRaisesRegex(ValueError, "size is unreasonable"):
            m.validate_archive(MetadataArchive(info))
        info.file_size, info.compress_size = 2 * 1024 * 1024, 10
        with self.assertRaisesRegex(ValueError, "expansion ratio"):
            m.validate_archive(MetadataArchive(info))

    def test_safe_legacy_filename_decoding_cannot_hide_an_unsafe_original_spelling(self):
        class MetadataArchive:
            def __init__(self, info): self.info = info
            def infolist(self): return [self.info]
        info = zipfile.ZipInfo("safe-decoded.xlsx")
        info.orig_filename = "safe-legacy-spelling.xlsx"
        self.assertIn("safe-decoded.xlsx", m.validate_archive(MetadataArchive(info)))
        info.orig_filename = "../../outside.xlsx"
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
            m.validate_archive(MetadataArchive(info))

    def test_sheet_dtd_duplicate_coordinates_and_huge_rectangles_are_rejected(self):
        for replacement, expected in (
                (b'<!DOCTYPE worksheet [<!ENTITY x "bad">]><worksheet/>', "DTD/entity"),
                (b'<worksheet><sheetData><row r="1"><c r="A1"/><c r="a1"/></row></sheetData></worksheet>', "duplicate cell"),
                (b'<worksheet><dimension ref="A1:XFD1048576"/><sheetData/></worksheet>', "CSV cell limit")):
            stream = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(synthetic_xlsx())) as original, zipfile.ZipFile(stream, "w") as target:
                for info in original.infolist():
                    target.writestr(info.filename, replacement if info.filename == "xl/worksheets/sheet1.xml" else original.read(info))
            with self.assertRaisesRegex(ValueError, expected):
                m.inspect_xlsx(stream.getvalue())

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_output_cannot_overwrite_or_enter_the_skill_distribution(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, contract = originals(base)
            existing = base / "existing"
            existing.mkdir()
            sentinel = existing / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NEW directory"):
                m.prepare(contract, existing)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            with self.assertRaisesRegex(ValueError, "outside the skill distribution"):
                m.prepare(contract, ROOT / "qa/should-never-copy-case-materials-here")

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_user_git_project_can_prepare_new_materials_without_changing_originals_or_git(self):
        for worktree_marker in (False,True):
            with self.subTest(worktree_marker=worktree_marker), tempfile.TemporaryDirectory() as folder:
                base=Path(folder)
                archive,contract=originals(base)
                before=archive.read_bytes()
                project=base/'user-contest-project'
                project.mkdir()
                marker=project/'.git'
                if worktree_marker:
                    marker.write_text('gitdir: user-managed-worktree\n',encoding='utf-8')
                    marker_before=marker.read_bytes()
                else:
                    marker.mkdir()
                    (marker/'config').write_text('user-owned-config\n',encoding='utf-8')
                    marker_before=(marker/'config').read_bytes()
                output=project/'data'/'original-materials-new'
                report=m.prepare(contract,output)
                self.assertEqual(report['status'],'prepared')
                self.assertEqual(len(report['files']),3)
                self.assertEqual(archive.read_bytes(),before)
                retained=marker.read_bytes() if worktree_marker else (marker/'config').read_bytes()
                self.assertEqual(retained,marker_before)
                self.assertFalse((project/'.gitignore').exists())
                self.assertTrue((output/'raw/statement/problem.pdf').is_file())

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_selected_member_must_match_exactly_and_missing_role_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            contract = manifest()
            contract["inputs"][0]["member"] = "input/RAW.xlsx"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact fixed member"):
                m.prepare(path, base / "new-output")
            self.assertFalse((base / "new-output").exists())

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_text_failure_retains_every_original_page_image_without_claiming_formula_success(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            with patch.object(pymupdf.Page, "get_text", side_effect=RuntimeError("synthetic extraction failure")):
                report = m.prepare(path, base / "research")
            self.assertEqual(report["status"], "prepared_with_limitations")
            primary = report["files"][0]
            self.assertEqual(len(primary["pdf"]["pages"]), 4)
            self.assertTrue(all(page["text_extraction_error"] for page in primary["pdf"]["pages"]))
            for page in primary["pdf"]["pages"]:
                self.assertTrue((base / "research" / primary["exports_directory"] / page["png"]).exists())
            self.assertTrue((base / "research" / primary["raw_path"]).exists())
            self.assertFalse(report["scientific_semantics_verified"])

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_question_page_binding_cannot_exceed_original_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            contract = manifest()
            contract["questions"][3]["source_pages"] = [5]
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceeds complete original PDF"):
                m.prepare(path, base / "research")
            report = json.loads((base / "research/file_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "preparation_failed")
            self.assertFalse(report["handoff_ready"])

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_cli_prepares_a_complete_synthetic_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            output = base / "independent-research"
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/prepare_case_materials.py"),
                                     "--manifest", str(path), "--output", str(output)],
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "prepared")
            receipt = json.loads((output / "file_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(receipt["files"][0]["pdf"]["pages"]), 4)

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_legacy_chinese_member_encoding_is_explicit_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            archive_path, contract_path = originals(base)
            stream = io.BytesIO()
            with zipfile.ZipFile(archive_path) as original, zipfile.ZipFile(stream, "w") as encoded:
                for info in original.infolist():
                    encoded.writestr("abcd.pdf" if info.filename == "problem.pdf" else info.filename, original.read(info))
            archive_path.write_bytes(stream.getvalue().replace(b"abcd.pdf", "题面.pdf".encode("gbk")))
            contract = manifest()
            contract["statement"].update({"member": "题面.pdf", "filename_encoding": "gbk"})
            contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
            report = m.prepare(contract_path, base / "research")
            self.assertEqual(report["status"], "prepared")
            self.assertEqual(report["files"][0]["filename_encoding"], "gbk")
            self.assertTrue((base / "research" / report["files"][0]["raw_path"]).exists())

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_missing_pdf_adapter_is_reported_without_fabricated_previews(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            with patch.dict(sys.modules, {"pymupdf": None}):
                report = m.prepare(path, base / "research")
            self.assertEqual(report["status"], "prepared_with_limitations")
            self.assertFalse(report["capabilities"]["pdf_page_previews"])
            self.assertFalse(report["capabilities"]["pdf_text_extraction"])
            self.assertTrue((base / "research" / report["files"][0]["raw_path"]).exists())
            self.assertFalse(report["completeness"]["question_source_pages_checked"])

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_explicit_supplementary_documents_text_csv_and_images_are_not_omitted(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            payloads = {"rules.doc": b"synthetic legacy DOC bytes", "rules.docx": b"synthetic DOCX bytes",
                        "rules.txt": "完整格式规则\n保留所有行\n".encode("utf-8"),
                        "notes.md": b"# Source notes\nKeep all content.\n",
                        "data.csv": b"time,value\n1.0000,003.140000\n2,\n",
                        "image.png": b"\x89PNG\r\n\x1a\nsynthetic original image"}
            contract = manifest()
            for index, (filename, data) in enumerate(payloads.items()):
                (base / filename).write_bytes(data)
                ident = f"supplement-{index}"
                contract["inputs"].append({"id": ident, "role": ident, "path": filename,
                                           "label": filename, "kind": "statement-supplement"})
                contract["required_roles"].append(ident)
            path.write_text(json.dumps(contract), encoding="utf-8")
            report = m.prepare(path, base / "research")
            self.assertEqual(len(report["files"]), 3 + len(payloads))
            self.assertEqual(report["status"], "prepared_with_limitations")
            for item in report["files"][3:]:
                original = payloads[item["label"]]
                self.assertEqual((base / "research" / item["raw_path"]).read_bytes(), original)
                self.assertEqual(item["sha256"], hashlib.sha256(original).hexdigest())
                if Path(item["label"]).suffix in {".txt", ".md", ".csv"}:
                    readable = base / "research" / item["content_extraction"]["path"]
                    self.assertEqual(readable.read_bytes(), original)
                else:
                    self.assertEqual(item["content_extraction"]["status"], "not-covered")
                self.assertTrue(item["review_required"])

    @unittest.skipIf(pymupdf is None, "PDF fixture needs existing PyMuPDF")
    def test_executable_source_is_not_silently_accepted_as_data(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            _, path = originals(base)
            (base / "solver.py").write_bytes(b"print('do not execute')")
            contract = manifest()
            contract["inputs"].append({"id": "old-solver", "role": "data", "path": "solver.py", "label": "not an original input"})
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "executable scripts"):
                m.prepare(path, base / "research")
            self.assertFalse((base / "research").exists())


if __name__ == "__main__":
    unittest.main()
