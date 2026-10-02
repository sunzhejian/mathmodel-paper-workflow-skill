import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate_template_decisions.py"
SPEC = importlib.util.spec_from_file_location("validate_template_decisions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TemplateDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        config = self.project / ".mathmodel/paper"
        config.mkdir(parents=True)
        (config / "config.json").write_text(json.dumps({
            "template": {"id": "cumcm", "entryFile": "document.tex", "source": "builtin"}
        }), encoding="utf-8")
        self.skill = self.root / "skill"
        paper = self.skill / "vendor/MathModelAgent/skills/5writing/templates/zh/cumcm-latex"
        paper.mkdir(parents=True)
        (paper / "main.tex").write_text("", encoding="utf-8")
        typst = paper.parent / "cumcm"
        typst.mkdir()
        (typst / "main.typ").write_text("", encoding="utf-8")
        diagram = self.skill / "vendor/sci-box/skills/scibox-diagram/assets/roadmap-5band"
        diagram.mkdir(parents=True)
        (diagram / "example.json").write_text("{}", encoding="utf-8")
        figure = self.skill / "vendor/MathModelAgent/skills/mathmodel-figure-templates"
        (figure / "references").mkdir(parents=True)
        (figure / "scripts/templates").mkdir(parents=True)
        (figure / "references/figure-catalog.md").write_text(
            "| `paired-raincloud` | `make_paired_raincloud.py` | 配对云雨图 |\n", encoding="utf-8")
        (figure / "scripts/templates/make_paired_raincloud.py").write_text("", encoding="utf-8")
        (self.project / "results").mkdir()
        (self.project / "results/real.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        self.record = self.project / "reports/template-decisions.json"
        self.record.parent.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, records):
        self.record.write_text(json.dumps({"decisions": records}), encoding="utf-8")
        return MODULE.validate(self.project, self.record, self.skill)

    def test_valid_choices_keep_separate_sources(self):
        result = self.write([
            {"kind": "paper", "target": "main", "choice": "cumcm-latex", "basis": "project-config"},
            {"kind": "diagram", "target": "roadmap", "choice": "roadmap-5band", "basis": "user"},
            {"kind": "data-figure", "target": "validation", "choice": "paired-raincloud",
             "basis": "user", "source_data": "results/real.csv", "simulated_data_replaced": True},
        ])
        self.assertTrue(result["passed"], result["findings"])
        self.assertEqual(len(result["checked"]), 3)

    def test_rejects_stale_or_unsubstantiated_choices(self):
        result = self.write([
            {"kind": "paper", "target": "main", "choice": "mcm-latex", "basis": "project-config"},
            {"kind": "diagram", "target": "roadmap", "choice": "missing-template", "basis": "user"},
            {"kind": "data-figure", "target": "chart", "choice": "paired-raincloud",
             "basis": "inferred", "source_data": "results/real.csv"},
            {"kind": "diagram", "target": "roadmap", "choice": "custom", "basis": "user"},
        ])
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["findings"]), 5)

    def test_empty_record_cannot_silence_future_questions(self):
        self.record.write_text('{"decisions":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            MODULE.validate(self.project, self.record, self.skill)

    def test_project_config_cannot_claim_another_engine(self):
        result = self.write([
            {"kind": "paper", "target": "main", "choice": "cumcm", "basis": "project-config"}
        ])
        self.assertIn("engine no longer matches", result["findings"][0])

    def test_ambiguous_language_must_be_recorded(self):
        for language in ("zh", "en"):
            folder = self.skill / f"vendor/MathModelAgent/skills/5writing/templates/{language}/mcm-latex"
            folder.mkdir(parents=True)
            (folder / "main.tex").write_text("", encoding="utf-8")
        result = self.write([
            {"kind": "paper", "target": "main", "choice": "mcm-latex", "basis": "user"}
        ])
        self.assertIn("ambiguous paper language", result["findings"][0])

    def test_ordinary_mathorcup_config_does_not_confirm_bigdata(self):
        config = self.project / ".mathmodel/paper/config.json"
        value = {"template":{"id":"mathorcup","entryFile":"main.tex","source":"builtin"}}
        config.write_text(json.dumps(value), encoding="utf-8")
        folder = self.skill / "assets/templates/zh/mathorcup-bigdata-latex"
        folder.mkdir(parents=True)
        (folder / "main.tex").write_text("Big Data template", encoding="utf-8")
        result = self.write([{"kind":"paper","target":"main","choice":"mathorcup-bigdata-latex","basis":"project-config"}])
        self.assertTrue(any("no longer matches config" in item for item in result["findings"]))
        result = self.write([{"kind":"paper","target":"main","choice":"mathorcup-bigdata-latex","basis":"user"}])
        self.assertTrue(result["passed"], result["findings"])
        self.assertEqual(json.loads(config.read_text(encoding="utf-8")), value)


if __name__ == "__main__":
    unittest.main()
