import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_vendor_skills.py"
SPEC = importlib.util.spec_from_file_location("check_vendor_skills", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VendorSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "examples").mkdir()
        entry = self.root / "vendor" / "Example" / "skills" / "example"
        entry.mkdir(parents=True)
        (entry / "SKILL.md").write_text("---\nname: example\ndescription: Example.\n---\n", encoding="utf-8")
        (self.root / "examples/upstream-lock.json").write_text(json.dumps({"sources": [
            {"name": "Example", "url": "https://example.org/project", "commit": "abc123"}
        ]}), encoding="utf-8")
        (self.root / "vendor/skill-integrations.json").write_text(json.dumps({"skills": [
            {"name": "example", "source": "Example", "path": "skills/example/SKILL.md",
             "stage": "demo", "usage": "conditional"}
        ]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_matching_commit_source_and_frontmatter(self):
        def command(args, **_):
            stdout = "abc123" if "rev-parse" in args else "https://example.org/project.git"
            return type("Result", (), {"returncode": 0, "stdout": stdout})()

        with patch.object(MODULE.subprocess, "run", side_effect=command):
            result = MODULE.inspect(self.root)
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["checked_skills"][0]["name"], "example")

    def test_mismatch_is_reported(self):
        (self.root / "vendor/Example/skills/example/SKILL.md").write_text(
            "---\nname: wrong-name\n---\n", encoding="utf-8")

        def command(args, **_):
            stdout = "wrong-commit" if "rev-parse" in args else "https://example.org/wrong.git"
            return type("Result", (), {"returncode": 0, "stdout": stdout})()

        with patch.object(MODULE.subprocess, "run", side_effect=command):
            result = MODULE.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["findings"]), 3)


if __name__ == "__main__":
    unittest.main()
