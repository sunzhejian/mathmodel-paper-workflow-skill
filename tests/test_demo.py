import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoTests(unittest.TestCase):
    def test_complete_synthetic_pipeline_and_no_overwrite(self):
        demo = load('run_demo')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'demo'
            report = demo.run(output)
            self.assertTrue(report['passed'])
            self.assertEqual(report['total_pages'], 4)
            self.assertEqual(report['appendix_pages_verified'], 2)
            self.assertEqual(report['rows'], 21)
            self.assertTrue((output/'pages'/'contact_001.png').exists())
            self.assertEqual(json.loads((output/'demo-report.json').read_text(encoding='utf-8')), report)
            before = (output/'final.pdf').read_bytes()
            with self.assertRaises(FileExistsError):
                demo.run(output)
            self.assertEqual((output/'final.pdf').read_bytes(), before)

    def test_diagram_generation_is_deterministic_and_editable(self):
        diagrams = load('generate_diagrams')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagrams.generate(root)
            files = sorted(root.glob('*.drawio'))
            self.assertEqual(len(files), 3)
            before = {p.name: p.read_bytes() for p in files}
            diagrams.generate(root)
            for path in files:
                self.assertEqual(path.read_bytes(), before[path.name])
                cells = list(ET.parse(path).iter('mxCell'))
                self.assertEqual(len(cells), len({c.get('id') for c in cells}))
                self.assertTrue(any(c.get('vertex') == '1' for c in cells))
                self.assertTrue(any(c.get('edge') == '1' for c in cells))


if __name__ == '__main__':
    unittest.main()
