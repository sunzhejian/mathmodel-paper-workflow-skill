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
            self.assertTrue(report['delivery_verified'])
            self.assertTrue(report['inventory_complete'])
            inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
            self.assertTrue(inventory['inventory_complete'])
            self.assertFalse(inventory['questions'][0]['run_command_executed_by_checker'])
            self.assertFalse(inventory['deliverables'][2]['present'])
            self.assertEqual(report['rows'], 21)
            self.assertTrue((output/'pages'/'contact_001.png').exists())
            self.assertTrue(json.loads((output/'delivery.json').read_text(encoding='utf-8'))['passed'])
            gate = load('verify_delivery')
            arguments = [output/'body.pdf', output/'original.pdf', output/'final.pdf',
                         output/'layout.json', output/'appendix.json',
                         output/'support.zip', output/'support']
            self.assertTrue(gate.verify(*arguments)['passed'])
            with (output/'final.pdf').open('ab') as stream:
                stream.write(b'\nchanged-after-appendix-check')
            self.assertIn('final PDF hash is stale or mismatched', gate.verify(*arguments)['failures'])
            with (output/'support/results/series.csv').open('a', encoding='utf-8') as stream:
                stream.write('stale,0\n')
            self.assertIn('Support source differs from ZIP: results/series.csv',
                          gate.verify(*arguments)['failures'])
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
