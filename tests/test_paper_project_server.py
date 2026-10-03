"""Boundary and observable rendering-tool behavior; no competition files used."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zlib

from PIL import Image
import pymupdf

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/paper_project_server.py"
SPEC = importlib.util.spec_from_file_location("paper_project_server", SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

CONTRACT = {"schema_version": 1, "engine": "typst",
            "fonts": {"body": "SimSun", "heading": "SimHei", "latin": "Times New Roman"},
            "body_size_pt": 12, "margins_cm": 2.5, "figure_width_mm": 160,
            "minimum_dpi": 300, "minimum_pages": 21}
GRAPH = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="n" value="Demand" vertex="1" parent="1"><mxGeometry x="10" y="10" width="680" height="100" as="geometry"/></mxCell></root></mxGraphModel>'
DRAWING = '<mxfile modified="old"><diagram id="page">' + GRAPH + '</diagram></mxfile>'


def svg_with_source(source=DRAWING):
    element = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "content": source})
    ET.SubElement(element, "foreignObject").text = "Demand label"
    return ET.tostring(element, encoding="unicode")


class ProjectToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "case"
        self.workspace.mkdir()
        self.project = self.root / "project"
        (self.project / "references").mkdir(parents=True)
        (self.project / "vendor/Example/skills/registered").mkdir(parents=True)
        (self.project / "vendor/Example/skills/registered/templates/zh/cumcm").mkdir(parents=True)
        (self.project / "vendor/Example/skills/registered/references").mkdir()
        (self.project / "vendor/Example/skills/registered/qa").mkdir()
        (self.project / "vendor/Example/skills/unregistered").mkdir(parents=True)
        (self.project / "qa").mkdir()
        (self.project / "SKILL.md").write_text("Project rules", encoding="utf-8")
        (self.project / "references/rendering-contract.md").write_text("Check real fonts and SVG", encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/SKILL.md").write_text("Registered stage", encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/templates/zh/cumcm/main.typ").write_text('#pagebreak()\n= 正文\n', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/templates/main.tex").write_text('\\newpage\n正文\n', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/templates/config.json").write_text('{"template":"registered"}', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/references/layout.md").write_text('摘要后明确分页', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/qa/private.md").write_text('Hidden evaluation', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/secret.json").write_text('Hidden credentials', encoding="utf-8")
        (self.project / "vendor/Example/skills/registered/templates/execute.py").write_text('print("unsupported")', encoding="utf-8")
        (self.project / "vendor/Example/skills/unregistered/SKILL.md").write_text("Unregistered stage", encoding="utf-8")
        (self.project / "vendor/Example/skills/unregistered/main.typ").write_text('Unregistered template', encoding="utf-8")
        (self.project / "vendor/Example/shared.md").write_text('Outside registered directory', encoding="utf-8")
        (self.project / "qa/private.md").write_text("Private evaluation", encoding="utf-8")
        (self.project / "vendor/skill-integrations.json").write_text(json.dumps({"skills": [{"name": "registered", "source": "Example", "path": "skills/registered/SKILL.md"}]}), encoding="utf-8")
        self.compiler = self.root / "compiler.exe"
        self.compiler.write_text("host-selected compiler", encoding="utf-8")
        self.drawio = self.root / "drawio.exe"
        self.drawio.write_text("host-selected renderer", encoding="utf-8")
        self.prose = "正文模型 y = 1，误差不可改。\n"
        self.original = '#set text(font: "Wrong", size: 11.5pt)\n#show heading.where(level: 1): set text(size: 18pt, weight: "bold")\n' + self.prose + '#figure(image("figures/mechanism.svg", width: 160mm), caption: [需求时序])\n'
        (self.workspace / "main.typ").write_text(self.original, encoding="utf-8")
        (self.workspace / "rendering-contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")
        (self.workspace / "figures").mkdir()
        (self.workspace / "figures/mechanism.drawio").write_text(DRAWING, encoding="utf-8")
        (self.workspace / "figures/mechanism.svg").write_text(svg_with_source(), encoding="utf-8")
        self.server = self.new_server()

    def new_server(self):
        return m.ProjectServer(self.workspace, self.compiler, drawio=self.drawio, project_root=self.project)

    def result(self, name, arguments=None):
        return self.server.call_tool(name, arguments or {})["structuredContent"]

    def fake_run(self, args, **kwargs):
        if args[1] == "--version":
            return subprocess.CompletedProcess(args, 0, "typst 0.test", "")
        if "--export" in args:
            output = Path(args[args.index("--output") + 1])
            if output.suffix == ".png":
                Image.new("RGB", (2040, 600), "white").save(output)
            else:
                with pymupdf.open() as document:
                    document.new_page()
                    document.save(output)
        if len(args) > 1 and args[1] == "compile":
            with pymupdf.open() as document:
                document.new_page().insert_text((30, 30), "actual candidate")
                document.save(Path(args[-1]))
        return subprocess.CompletedProcess(args, 0, "", "")

    def test_paths_refuse_traversal_absolute_credentials_and_qa(self):
        for path in ("../outside.txt", "C:/secrets.txt", "/etc/passwd", "file:///secret", "main.typ:stream", ".env", "provider-credentials.json", "qa/private.md"):
            with self.subTest(path=path):
                result = self.result("read_workspace_file", {"path": path})
                self.assertFalse(result["passed"])
        self.assertEqual(self.result("read_workspace_file", {"path": "main.typ"})["content"], self.original)

    def test_only_registered_vendor_entrypoint_is_readable(self):
        self.assertEqual(self.result("read_project_file", {"path": "vendor/Example/skills/registered/SKILL.md"})["content"], "Registered stage")
        for path in ("scripts/paper_project_server.py", "vendor/Example/skills/unregistered/SKILL.md", "qa/private.md", "vendor/../SKILL.md"):
            with self.subTest(path=path):
                self.assertFalse(self.result("read_project_file", {"path": path})["passed"])

    def test_registered_vendor_templates_and_references_are_actually_readable(self):
        samples = {
            "templates/zh/cumcm/main.typ": '#pagebreak()\n= 正文\n',
            "templates/main.tex": '\\newpage\n正文\n',
            "templates/config.json": '{"template":"registered"}',
            "references/layout.md": '摘要后明确分页',
        }
        for relative, expected in samples.items():
            with self.subTest(path=relative):
                result = self.result("read_project_file", {"path": "vendor/Example/skills/registered/" + relative})
                self.assertEqual(result["content"], expected)

    def test_registered_vendor_read_does_not_open_siblings_private_or_executable_files(self):
        for path in ("vendor/Example/skills/unregistered/main.typ", "vendor/Example/shared.md",
                     "vendor/Example/skills/registered/../unregistered/main.typ",
                     "vendor/Example/skills/registered/qa/private.md",
                     "vendor/Example/skills/registered/secret.json",
                     "vendor/Example/skills/registered/templates/execute.py"):
            with self.subTest(path=path):
                self.assertFalse(self.result("read_project_file", {"path": path})["passed"])

    def summary_case(self):
        summary = {"separate_page": True, "max_pages": 1, "heading": "Summary", "body_heading": "Body"}
        contract = {**CONTRACT, "summary": summary}
        (self.workspace / "rendering-contract.json").write_text(json.dumps(contract), encoding="utf-8")
        source = '#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n*Summary*\n摘要模型 y = 1。\n*关键词：* demand model\n= Body\n' + self.prose
        (self.workspace / "main.typ").write_text(source, encoding="utf-8")
        return summary, source

    def summary_pdf(self, path, *, shared=False, overflow=False):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((30, 30), "Summary", fontsize=16)
            page.insert_text((30, 65), "Demand model and numerical result", fontsize=11)
            if shared:
                page.insert_text((30, 90), '关键词： demand model', fontname="china-s", fontsize=11)
                page.insert_text((30, 130), "Body", fontsize=16)
            else:
                if overflow:
                    continuation = document.new_page()
                    continuation.insert_text((30, 30), "More summary content", fontsize=11)
                    continuation.insert_text((30, 65), '关键词： demand model', fontname="china-s", fontsize=11)
                else:
                    page.insert_text((30, 90), '关键词： demand model', fontname="china-s", fontsize=11)
                document.new_page().insert_text((30, 30), "Body", fontsize=16)
            document.save(path)

    def test_no_summary_contract_does_not_force_summary_rule_or_change_source(self):
        original = (self.workspace / "main.typ").read_bytes()
        with patch.object(m.summary_guard, "ensure_separation") as helper:
            result = self.result("ensure_summary_page")
        helper.assert_not_called()
        self.assertEqual(result["status"], "not_required")
        self.assertFalse(result["changed"])
        self.assertEqual(original, (self.workspace / "main.typ").read_bytes())

    def test_summary_page_tool_preserves_science_and_is_repeatable(self):
        _, original = self.summary_case()
        result = self.result("ensure_summary_page")
        self.assertTrue(result["scientific_text_preserved"])
        self.assertTrue(result["changed"])
        after = (self.workspace / "main.typ").read_bytes()
        self.assertIn(b"#pagebreak()", after)
        text = after.decode("utf-8").replace("\r\n", "\n")
        self.assertIn(self.prose, text)
        self.assertIn('摘要模型 y = 1。', text)
        self.assertIn('*Summary*', text)
        self.assertIn('= Body', text)
        repeated = self.result("ensure_summary_page")
        self.assertFalse(repeated["changed"])
        self.assertEqual(after, (self.workspace / "main.typ").read_bytes())

    def test_summary_helper_cannot_change_scientific_body_and_rolls_back(self):
        summary, original = self.summary_case()
        before = (self.workspace / "main.typ").read_bytes()
        def bad_helper(source, contract):
            source.write_text(original.replace("y = 1", "y = 99"), encoding="utf-8")
            return {"changed": True}
        with patch.object(m.summary_guard, "ensure_separation", side_effect=bad_helper):
            result = self.result("ensure_summary_page")
        self.assertFalse(result["passed"])
        self.assertEqual(before, (self.workspace / "main.typ").read_bytes())

    def test_inspect_reports_actual_required_summary_boundary(self):
        self.summary_case()
        self.summary_pdf(self.workspace / "main.pdf", shared=True)
        with patch.object(self.server, "run", side_effect=self.fake_run), patch.object(m.guard, "font_names", return_value=set(CONTRACT["fonts"].values())):
            result = self.result("inspect_rendering")
        self.assertTrue(result["summary_check_required"])
        self.assertFalse(result["summary_check"]["passed"])
        self.assertTrue(result["summary_check"]["same_page"])

    def test_required_same_page_or_overflowing_summary_does_not_replace_accepted_pdf(self):
        self.summary_case()
        target = self.workspace / "main.pdf"
        for shared, overflow in ((True, False), (False, True)):
            with self.subTest(shared=shared, overflow=overflow):
                target.write_bytes(b"previous accepted PDF must remain")
                def candidate(args, **kwargs):
                    self.summary_pdf(Path(args[-1]), shared=shared, overflow=overflow)
                    return subprocess.CompletedProcess(args, 0, "", "")
                with patch.object(self.server, "run", side_effect=candidate), patch.object(m.guard, "pdf_font_check", return_value={"passed": True, "pages": 21}):
                    result = self.result("compile_and_check")
                self.assertTrue(result["compiled"])
                self.assertTrue(result["font_and_page_check_passed"])
                self.assertFalse(result["passed"])
                self.assertFalse(result["output_accepted"])
                self.assertEqual(target.read_bytes(), b"previous accepted PDF must remain")
                self.assertEqual(result["summary_check"]["same_page"], shared)
                self.assertEqual(result["summary_check"]["overflow"], overflow)

    def test_summary_contract_and_actual_boundary_must_both_pass_for_publication(self):
        self.summary_case()
        def candidate(args, **kwargs):
            self.summary_pdf(Path(args[-1]))
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch.object(self.server, "run", side_effect=candidate), patch.object(m.guard, "pdf_font_check", return_value={"passed": True, "pages": 21}):
            result = self.result("compile_and_check")
        self.assertTrue(result["passed"])
        self.assertTrue(result["summary_check"]["passed"])
        self.assertTrue((self.workspace / "main.pdf").is_file())

    def test_actual_hard_link_is_refused(self):
        outside = self.root / "outside.txt"
        outside.write_text("private text", encoding="utf-8")
        alias = self.workspace / "alias.txt"
        os.link(outside, alias)
        self.assertFalse(self.result("read_workspace_file", {"path": "alias.txt"})["passed"])

    def test_actual_symlink_or_junction_is_refused(self):
        external = self.root / "external"
        external.mkdir()
        (external / "note.txt").write_text("outside", encoding="utf-8")
        link = self.workspace / "linked"
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("This host cannot create a directory symlink")
            process = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(external)], capture_output=True)
            if process.returncode:
                self.skipTest("This host cannot create a directory junction")
        try:
            self.assertFalse(self.result("read_workspace_file", {"path": "linked/note.txt"})["passed"])
        finally:
            if os.name == "nt" and not link.is_symlink():
                os.rmdir(link)
            else:
                link.unlink()

    def test_sanitized_environment_is_used_for_actual_subprocess_calls(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "top-secret-value", "DEEPSEEK_API_KEY": "provider-secret-key"}):
            server = self.new_server()
            with patch.object(m.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                server.run([str(self.compiler), "--version"])
            env = run.call_args.kwargs["env"]
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("DEEPSEEK_API_KEY", env)
            self.assertEqual(server.sanitize("compiler echoes top-secret-value"), "compiler echoes [redacted]")

    def test_numeric_token_count_is_returned_exactly_without_silent_redaction(self):
        original='{"access_token_count":123}\n'
        (self.workspace / 'metrics.json').write_text(original,encoding='utf-8')
        result=self.result('read_workspace_file',{'path':'metrics.json'})
        self.assertEqual(result['content'],original)
        self.assertEqual(json.loads(result['content']),{'access_token_count':123})
        self.assertFalse(result['sanitized'])
        audit=json.loads((self.workspace / 'project-tool-events.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        self.assertEqual(audit['result_summary']['returned_range'],[1,1])
        self.assertEqual(audit['result_summary']['returned_content_sha256'],result['returned_content_sha256'])
        self.assertNotIn('access_token_count',json.dumps(audit))

    def test_known_credential_in_text_is_refused_instead_of_changing_material(self):
        with patch.dict(os.environ,{'SYNTHETIC_API_KEY':'synthetic-private-value'}):
            server=self.new_server()
        (self.workspace / 'input.txt').write_text('synthetic-private-value',encoding='utf-8')
        result=server.call_tool('read_workspace_file',{'path':'input.txt'})['structuredContent']
        self.assertFalse(result['passed'])
        self.assertNotIn('synthetic-private-value',json.dumps(result))
        self.assertEqual((self.workspace / 'input.txt').read_text(encoding='utf-8'),'synthetic-private-value')

    def test_foreignobject_and_wrong_fonts_are_observed(self):
        with patch.object(self.server, "run", side_effect=self.fake_run), patch.object(m.guard, "font_names", return_value=set(CONTRACT["fonts"].values())):
            result = self.result("inspect_rendering")
        self.assertTrue(result["engine_available"])
        self.assertFalse(result["profile_declarations_conform"])
        self.assertFalse(result["images"][0]["direct_embedding_ready"])
        self.assertIn("foreignObject", result["images"][0]["reasons"][0])

    def test_apply_profile_preserves_scientific_text_and_is_repeatable(self):
        with patch.object(m.guard, "font_names", return_value=set(CONTRACT["fonts"].values())):
            result = self.result("apply_font_profile")
            self.assertTrue(result["scientific_text_preserved"])
            after = (self.workspace / "main.typ").read_bytes()
            self.result("apply_font_profile")
        text = after.decode("utf-8").replace("\r\n", "\n")
        self.assertIn(self.prose, text)
        self.assertIn('#figure(image("figures/mechanism.svg", width: 160mm), caption: [需求时序])', text)
        self.assertEqual(after, (self.workspace / "main.typ").read_bytes())
        self.assertIn("SimSun", text)
        self.assertIn("SimHei", text)

    def test_font_helper_cannot_change_body_and_rolls_back(self):
        def bad_helper(source, *args, **kwargs):
            source.write_text(self.original.replace("y = 1", "y = 99"), encoding="utf-8")
            return {"changed": True}
        with patch.object(m.guard, "apply_profile", side_effect=bad_helper):
            result = self.result("apply_font_profile")
        self.assertFalse(result["passed"])
        self.assertEqual((self.workspace / "main.typ").read_text(encoding="utf-8"), self.original)

    def test_compiler_is_not_invoked_while_bad_svg_is_referenced(self):
        with patch.object(self.server, "run") as run:
            result = self.result("compile_and_check")
        self.assertFalse(result["passed"])
        self.assertFalse(result["compiled"])
        run.assert_not_called()
        self.assertFalse((self.workspace / "main.pdf").exists())

    def test_imported_bad_svg_and_dynamic_images_are_refused(self):
        (self.workspace / "main.typ").write_text('#include "included.typ"\n', encoding="utf-8")
        (self.workspace / "included.typ").write_text('#image("figures/mechanism.svg")', encoding="utf-8")
        self.assertFalse(self.result("compile_and_check")["passed"])
        (self.workspace / "main.typ").write_text('#let path = "figures/mechanism.svg"\n#image(path)\n', encoding="utf-8")
        result = self.result("compile_and_check")
        self.assertFalse(result["passed"])
        self.assertTrue(result["source_scan_issues"])
        for expression in ('#let show-image = image\n#show-image("figures/mechanism.svg")', '#eval("image(foo)")'):
            (self.workspace / "main.typ").write_text(expression, encoding="utf-8")
            result = self.result("compile_and_check")
            self.assertFalse(result["passed"])
            self.assertTrue(result["source_scan_issues"])

    def test_invalid_event_path_prevents_mutation(self):
        (self.workspace / "project-tool-events.jsonl").mkdir()
        with patch.object(m.guard, "apply_profile") as helper:
            result = self.result("apply_font_profile")
        self.assertFalse(result["passed"])
        helper.assert_not_called()
        self.assertEqual((self.workspace / "main.typ").read_text(encoding="utf-8"), self.original)

    def test_export_and_exact_image_adaptation_keep_prose_and_original_sources(self):
        original_svg = (self.workspace / "figures/mechanism.svg").read_bytes()
        original_drawing = (self.workspace / "figures/mechanism.drawio").read_bytes()
        self.assertFalse(self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})["passed"])
        with patch.object(self.server, "run", side_effect=self.fake_run):
            exported = self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        self.assertTrue(exported["passed"])
        self.assertGreaterEqual(exported["effective_dpi"], 300)
        result = self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})
        self.assertTrue(result["changed"])
        self.assertEqual(result["replacements"], 1)
        self.assertEqual((self.workspace / "main.typ").read_text(encoding="utf-8"), self.original.replace('image("figures/mechanism.svg"', 'image("figures/mechanism.png"'))
        self.assertEqual(original_svg, (self.workspace / "figures/mechanism.svg").read_bytes())
        self.assertEqual(original_drawing, (self.workspace / "figures/mechanism.drawio").read_bytes())
        self.assertTrue((self.workspace / "figures/mechanism.pdf").exists())
        unchanged=(self.workspace/'main.typ').read_bytes()
        second=self.result('use_compatible_image',{'svg':'figures/mechanism.svg'})
        self.assertFalse(second['changed']);self.assertEqual(second['status'],'already_using_verified_export')
        self.assertEqual(unchanged,(self.workspace/'main.typ').read_bytes())
        (self.workspace/'figures/mechanism.png').write_bytes(b'tampered')
        self.assertFalse(self.result('use_compatible_image',{'svg':'figures/mechanism.svg'})['passed'])

    def test_partial_reads_are_explicit_and_hash_whole_file(self):
        source=self.workspace/'long.md';source.write_text(''.join(str(i)+'\n' for i in range(1,202)),encoding='utf-8')
        first=self.result('read_workspace_file',{'path':'long.md'})
        self.assertTrue(first['truncated']);self.assertEqual(first['returned_range'],[1,160]);self.assertEqual(first['next_start_line'],161)
        second=self.result('read_workspace_file',{'path':'long.md','start_line':161,'max_lines':50})
        self.assertEqual(second['returned_range'],[161,201]);self.assertEqual(second['sha256'],first['sha256'])
        self.assertTrue(second['truncated'])  # The second window is not a whole-file read.
        self.assertEqual(first['content']+second['content'],source.read_text(encoding='utf-8'))
        for args in [{'start_line':True},{'start_line':0},{'max_lines':501},{'max_lines':1.5},{'unknown':1}]:
            self.assertFalse(self.result('read_workspace_file',{'path':'long.md',**args})['passed'])

    def test_changed_labels_cannot_claim_same_source(self):
        (self.workspace / "figures/mechanism.svg").write_text(svg_with_source(DRAWING.replace("Demand", "Other meaning")), encoding="utf-8")
        with patch.object(self.server, "run", side_effect=self.fake_run):
            self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        result = self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})
        self.assertFalse(result["passed"])
        self.assertEqual(self.original, (self.workspace / "main.typ").read_text(encoding="utf-8"))

    def test_startup_binding_is_frozen_and_missing_provenance_is_refused(self):
        svg = self.workspace / "figures/mechanism.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>', encoding="utf-8")
        drawing = self.workspace / "figures/mechanism.drawio"
        with patch.object(self.server, "run", side_effect=self.fake_run):
            self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        self.assertFalse(self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})["passed"])
        bindings = {"schema_version": 1, "bindings": [{"svg": "figures/mechanism.svg", "source": "figures/mechanism.drawio", "svg_sha256": m.sha256(svg), "source_sha256": m.sha256(drawing)}]}
        (self.workspace / "asset-bindings.json").write_text(json.dumps(bindings), encoding="utf-8")
        self.server = self.new_server()
        (self.workspace / "asset-bindings.json").write_text('{"schema_version":1,"bindings":[]}', encoding="utf-8")
        with patch.object(self.server, "run", side_effect=self.fake_run):
            self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        self.assertTrue(self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})["changed"])

    def test_tampered_export_and_small_png_are_rejected(self):
        with patch.object(self.server, "run", side_effect=self.fake_run):
            self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        Image.new("RGB", (40, 30)).save(self.workspace / "figures/mechanism.png")
        self.assertFalse(self.result("use_compatible_image", {"svg": "figures/mechanism.svg"})["passed"])
        (self.workspace / "main.typ").write_text('#image("figures/mechanism.png")\n', encoding="utf-8")
        with patch.object(self.server, "run") as run:
            result = self.result("compile_and_check")
        self.assertFalse(result["passed"])
        run.assert_not_called()

    def test_failed_pdf_font_or_page_check_does_not_replace_accepted_pdf(self):
        (self.workspace / "main.typ").write_text('#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n' + self.prose, encoding="utf-8")
        target = self.workspace / "main.pdf"
        target.write_bytes(b"previous accepted document")
        with patch.object(self.server, "run", side_effect=self.fake_run):
            result = self.result("compile_and_check")
        self.assertFalse(result["passed"])
        self.assertTrue(result["compiled"])
        self.assertEqual(result["pages"], 1)
        self.assertEqual(target.read_bytes(), b"previous accepted document")

    def test_successful_pdf_is_published_only_after_check_and_typst_root_is_fixed(self):
        (self.workspace / "main.typ").write_text('#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n' + self.prose, encoding="utf-8")
        with patch.object(self.server, "run", side_effect=self.fake_run) as run, patch.object(m.guard, "pdf_font_check", return_value={"passed": True, "pages": 21, "expected_fonts_present": {"body": True, "heading": True, "latin": True}}):
            result = self.result("compile_and_check")
        self.assertTrue(result["passed"])
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--root") + 1], str(self.workspace.resolve()))
        self.assertTrue((self.workspace / "main.pdf").is_file())

    def test_fragmented_relation_is_refused_before_compiler_and_source_is_unchanged(self):
        text='#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n' + '$ u_t $#text(" = ")$ y_t $#text(" + ")$ q_t $\n'
        source=self.workspace/'main.typ'
        source.write_text(text,encoding='utf-8')
        before=source.read_bytes()
        with patch.object(self.server,'run') as run:
            result=self.result('compile_and_check')
        self.assertFalse(result['passed'])
        self.assertFalse(result['compiled'])
        self.assertEqual(result['formula_status'],'fail')
        self.assertEqual(source.read_bytes(),before)
        run.assert_not_called()

    def test_pdf_formula_failure_cannot_replace_existing_accepted_output(self):
        (self.workspace/'main.typ').write_text('#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n'+self.prose,encoding='utf-8')
        accepted=self.workspace/'main.pdf'
        accepted.write_bytes(b'previous accepted output')
        with patch.object(self.server,'run',side_effect=self.fake_run), patch.object(m.guard,'pdf_font_check',return_value={'passed':True,'pages':21}), patch.object(m.formula_guard,'check_pdf',return_value={'status':'fail','passed':False,'review_required':True,'issues':[{'code':'pdf_fragmented_equation_run','severity':'error'}]}):
            result=self.result('compile_and_check')
        self.assertFalse(result['passed'])
        self.assertEqual(result['formula_status'],'fail')
        self.assertEqual(accepted.read_bytes(),b'previous accepted output')

    def test_formula_warning_is_reported_without_claiming_mathematical_certification(self):
        (self.workspace/'main.typ').write_text('#set text(font: ("Times New Roman", "SimSun"))\n#show heading: set text(font: "SimHei")\n'+self.prose,encoding='utf-8')
        with patch.object(self.server,'run',side_effect=self.fake_run), patch.object(m.guard,'pdf_font_check',return_value={'passed':True,'pages':21}), patch.object(m.formula_guard,'check_pdf',return_value={'status':'review','passed':False,'review_required':True,'issues':[{'code':'pdf_numbered_atomic_run','severity':'warning'}]}):
            result=self.result('compile_and_check')
        self.assertEqual(result['formula_status'],'review')
        self.assertTrue(result['formula_review_required'])
        self.assertIn('warnings require review',result['scope'])

    def test_wrong_top_level_font_cannot_pass_from_incidental_font_resources(self):
        (self.workspace / "main.typ").write_text('#set text(font: "Wrong")\n' + self.prose, encoding="utf-8")
        with patch.object(self.server, "run") as run:
            result = self.result("compile_and_check")
        self.assertFalse(result["passed"])
        self.assertFalse(result["compiled"])
        run.assert_not_called()

    def test_multiline_profile_and_raw_code_example_preserve_other_text(self):
        source = '#set text(\n  font: "Wrong",\n  tracking: .1pt,\n)\n' + self.prose + '```typ\n#image("unavailable-example.svg")\n```\n'
        (self.workspace / "main.typ").write_text(source, encoding="utf-8")
        with patch.object(m.guard, "font_names", return_value=set(CONTRACT["fonts"].values())), patch.object(self.server, "run", side_effect=self.fake_run):
            changed = self.result("apply_font_profile")
            inspected = self.result("inspect_rendering")
        self.assertTrue(changed["scientific_text_preserved"])
        self.assertTrue(inspected["profile_declarations_conform"])
        self.assertFalse(inspected["images"])
        after = (self.workspace / "main.typ").read_text(encoding="utf-8")
        self.assertIn(self.prose, after)
        self.assertIn('tracking: .1pt', after)
        self.assertIn('```typ\n#image("unavailable-example.svg")\n```', after)

    def test_events_record_hashes_and_summary_without_text_or_secrets(self):
        (self.workspace / "note.txt").write_text("private scientific prose", encoding="utf-8")
        self.result("read_workspace_file", {"path": "note.txt"})
        self.result("read_workspace_file", {"path": "../outside.txt"})
        lines = (self.workspace / "project-tool-events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertNotIn("private scientific prose", "".join(lines))
        event = json.loads(lines[0])
        self.assertEqual(event["source_hashes"]["workspace/note.txt"]["before_sha256"], m.sha256(self.workspace / "note.txt"))
        self.assertFalse(event["result_summary"]["is_error"])
        self.assertTrue(json.loads(lines[1])["result_summary"]["is_error"])

    def test_protocol_initialize_list_call_and_no_notification_reply(self):
        preflight = self.server.dispatch({"jsonrpc": "2.0", "id": 0, "method": "tools/list"})
        self.assertIn("error", preflight)
        initialized = self.server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test", "version": "1"}, "capabilities": {}}})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertIsNone(self.server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        listed = self.server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 8)
        called = self.server.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_workspace_file", "arguments": {"path": "main.typ"}}})
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(called["result"]["structuredContent"]["content"], self.original)

    def test_real_stdio_handshake_produces_only_jsonrpc_lines(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_workspace_file", "arguments": {"path": "main.typ"}}}]
        process = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.workspace), "--compiler", str(self.compiler)], input="\n".join(json.dumps(item) for item in messages) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        self.assertTrue(all(item["jsonrpc"] == "2.0" for item in responses))

    def test_actual_registered_upstream_template_read_through_stdio(self):
        relative = "vendor/MathModelAgent/skills/5writing/templates/zh/cumcm/main.typ"
        actual = SCRIPT.parents[1] / relative
        if not actual.is_file():
            self.skipTest("Pinned upstream templates are unavailable in this checkout")
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read_project_file", "arguments": {"path": relative}}}]
        process = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.workspace), "--compiler", str(self.compiler)], input="\n".join(json.dumps(item) for item in messages) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout.splitlines()[-1])["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["sha256"], m.sha256(actual))
        self.assertEqual(result["structuredContent"]["content"], actual.read_text(encoding="utf-8-sig"))

    def test_compressed_drawio_metadata_compares_cells_and_rejects_external_images(self):
        compressor = zlib.compressobj(wbits=-15)
        payload = compressor.compress(quote(GRAPH, safe="~()*!.'").encode("utf-8")) + compressor.flush()
        compressed = '<mxfile><diagram>' + base64.b64encode(payload).decode("ascii") + '</diagram></mxfile>'
        self.assertEqual(m.graph_signature(compressed), m.graph_signature(DRAWING))
        bad_graph = GRAPH.replace('value="Demand"', 'value="Demand" style="image=file:///C:/private.png;"')
        compressor = zlib.compressobj(wbits=-15)
        payload = compressor.compress(quote(bad_graph).encode("utf-8")) + compressor.flush()
        bad_drawing = '<mxfile><diagram>' + base64.b64encode(payload).decode("ascii") + '</diagram></mxfile>'
        (self.workspace / "figures/mechanism.drawio").write_text(bad_drawing, encoding="utf-8")
        with patch.object(self.server, "run") as run:
            result = self.result("export_diagram", {"source": "figures/mechanism.drawio"})
        self.assertFalse(result["passed"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
