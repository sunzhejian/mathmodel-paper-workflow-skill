import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/template_inventory.py"
SPEC = importlib.util.spec_from_file_location("template_inventory", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TemplateInventoryTests(unittest.TestCase):
    def test_reads_config_and_variants_without_exposing_team_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            folder = project / ".mathmodel/paper"
            folder.mkdir(parents=True)
            (folder / "config.json").write_text(json.dumps({
                "template": {"id": "cumcm", "source": "custom",
                             "entryFile": "document.tex", "sourcePath": "PRIVATE/custom.tex",
                             "name": {"zh-CN": "PRIVATE"}},
                "contestFields": [{"id": "teamNumber", "value": "PRIVATE"}],
                "teamProfile": {"phone": "PRIVATE"},
            }), encoding="utf-8")
            template = root / "skill/vendor/MathModelAgent/skills/5writing/templates/zh/cumcm-latex"
            template.mkdir(parents=True)
            (template / "main.tex").write_text("template", encoding="utf-8")
            typst = template.parent / "cumcm"
            typst.mkdir()
            (typst / "main.typ").write_text("template", encoding="utf-8")
            diagram = root / "skill/vendor/sci-box/skills/scibox-diagram/assets/roadmap-5band"
            diagram.mkdir(parents=True)
            (diagram / "example.json").write_text("{}", encoding="utf-8")
            (diagram / "preview.png").write_bytes(b"preview")
            figure = root / "skill/vendor/MathModelAgent/skills/mathmodel-figure-templates"
            (figure / "references").mkdir(parents=True)
            (figure / "scripts/templates").mkdir(parents=True)
            (figure / "references/figure-catalog.md").write_text(
                "| `paired-raincloud` | `make_paired_raincloud.py` | 配对云雨图 |\n",
                encoding="utf-8")
            (figure / "scripts/templates/make_paired_raincloud.py").write_text("", encoding="utf-8")
            result = MODULE.inspect(project, root / "skill")
            self.assertEqual(result["configured"]["id"], "cumcm")
            self.assertEqual(result["configured"]["engine"], "LaTeX")
            self.assertEqual(result["configured"]["matching_variants"], ["cumcm-latex"])
            self.assertTrue(result["configured"]["custom_source_present"])
            self.assertFalse(result["configured"]["custom_source_exists"])
            self.assertEqual({item["engine"] for item in result["available"]},
                             {"LaTeX", "Typst"})
            self.assertEqual(result["diagram_templates"][0]["id"], "roadmap-5band")
            self.assertEqual(result["data_figure_templates"][0]["id"], "paired-raincloud")
            self.assertIn("simulated", result["data_figure_templates"][0]["default_data"])
            self.assertNotIn("PRIVATE", json.dumps(result))
            self.assertFalse((project / "document.tex").exists())
            cli = subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(project),
                                  "--skill-root", str(root / "skill"), "--category", "paper",
                                  "--configured-family"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual({item["id"] for item in json.loads(cli.stdout)["choices"]},
                             {"cumcm", "cumcm-latex"})

    def test_missing_vendor_is_reported_without_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = MODULE.inspect(root, root)
            self.assertIsNone(result["configured"])
            self.assertEqual(result["available"], [])
            self.assertEqual(result["diagram_templates"], [])
            self.assertEqual(result["data_figure_templates"], [])
            self.assertFalse(result["vendor_templates_present"])


if __name__ == "__main__":
    unittest.main()
