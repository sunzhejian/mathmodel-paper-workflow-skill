import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preview_diagram_templates.py"
SPEC = importlib.util.spec_from_file_location("preview_diagram_templates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TemplatePreviewTests(unittest.TestCase):
    def test_builds_one_sheet_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "vendor/sci-box/skills/scibox-diagram/assets"
            for name in MODULE.TEMPLATES:
                folder = source / name
                folder.mkdir(parents=True)
                Image.new("RGB", (300, 500), "#aaccee").save(folder / "preview.png")
            output = root / "choices.png"
            MODULE.build(root, output)
            with Image.open(output) as picture:
                self.assertEqual(picture.size, (1472, 1192))
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                MODULE.build(root, output)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
