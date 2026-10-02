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

    def test_bigdata_has_separate_family_and_dated_rule_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            config = project / ".mathmodel/paper"
            config.mkdir(parents=True)
            original = '{"template":{"id":"mathorcup","entryFile":"main.tex","source":"builtin"}}'
            (config / "config.json").write_text(original, encoding="utf-8")
            skill = root / "skill"
            for name, entry in [("mathorcup-bigdata", "main.typ"), ("mathorcup-bigdata-latex", "main.tex")]:
                source = skill / "assets/templates/zh" / name
                source.mkdir(parents=True)
                (source / entry).write_text("synthetic template", encoding="utf-8")
                (source / "profile.json").write_text(json.dumps({"contest_family":"mathorcup-bigdata",
                    "format_rules_year":2025,"rules_status":"provisional","contest_year":2026}), encoding="utf-8")
            ordinary = skill / "vendor/MathModelAgent/skills/5writing/templates/zh/mathorcup-latex"
            ordinary.mkdir(parents=True)
            (ordinary / "main.tex").write_text("ordinary MathorCup", encoding="utf-8")
            result = MODULE.inspect(project, skill)
            self.assertEqual(result["configured"]["matching_variants"], ["mathorcup-latex"])
            candidates = [x for x in result["available"] if x.get("contest_family") == "mathorcup-bigdata"]
            self.assertEqual(len(candidates), 2)
            self.assertTrue(all(x["rules_status"] == "provisional" and x["format_rules_year"] == 2025 for x in candidates))
            cli = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "--project-root", str(project),
                                  "--skill-root", str(skill), "--category", "paper", "--family", "mathorcup-bigdata"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual({x["id"] for x in json.loads(cli.stdout)["choices"]}, {"mathorcup-bigdata", "mathorcup-bigdata-latex"})
            self.assertEqual((config / "config.json").read_text(encoding="utf-8"), original)

    def test_figure_inventory_distinguishes_style_from_data_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            base = skill / "vendor/MathModelAgent/skills/mathmodel-figure-templates"
            (base / "references").mkdir(parents=True)
            (base / "scripts/templates").mkdir(parents=True)
            (base / "references/figure-catalog.md").write_text(
                "| `correlation-pairgrid` | `make_grid.py` | Correlation |\n"
                "| `paired-raincloud` | `make_cloud.py` | Raincloud |\n", encoding="utf-8")
            for name in ("make_grid.py", "make_cloud.py"):
                (base / "scripts/templates" / name).write_text("", encoding="utf-8")
            (skill / "scripts").mkdir()
            (skill / "scripts/render_scientific_data.py").write_text("original adapter", encoding="utf-8")
            candidates = {x["id"]: x for x in MODULE.inspect(root, skill)["data_figure_templates"]}
            self.assertEqual(candidates["correlation-pairgrid"]["data_adapter"], "scripts/render_scientific_data.py")
            self.assertIsNone(candidates["paired-raincloud"]["data_adapter"])
            (skill / "scripts/render_scientific_data.py").unlink()
            self.assertTrue(all(x["data_adapter"] is None for x in MODULE.inspect(root, skill)["data_figure_templates"]))


if __name__ == "__main__":
    unittest.main()
