import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('workflow_check', Path(__file__).resolve().parents[1] / 'scripts/check_workflow_state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorkflowStateTests(unittest.TestCase):
    def test_changed_input_propagates_to_untouched_paper_and_restoring_content_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def file(name, text):
                (root / name).write_text(text, encoding='utf-8')
                return dict(path=name, sha256=hashlib.sha256(text.encode()).hexdigest())
            a, b, c = file('model.md', 'a'), file('result.csv', '3'), file('paper.tex', '3')
            state = dict(schema_version=1, checkpoints=[dict(stage='solve', inputs=[a], outputs=[b]), dict(stage='paper', inputs=[b], outputs=[c])])
            self.assertTrue(module.check_state(state, root)['current'])
            file('model.md', 'new')
            result = module.check_state(state, root)
            self.assertFalse(result['current'])
            self.assertEqual(result['checkpoints'][1]['upstream_stages'], ['solve'])
            self.assertFalse(result['scientific_verified'])
            file('model.md', 'a')
            self.assertTrue(module.check_state(state, root)['current'])
            (root / 'result.csv').unlink()
            self.assertFalse(module.check_state(state, root)['current'])

    def test_invalid_and_duplicate_paths_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            def state(name):
                return dict(schema_version=1, checkpoints=[dict(stage='x', inputs=[dict(path=name, sha256='0' * 64)], outputs=[dict(path='out', sha256='0' * 64)])])
            for name in ['../private', '/etc/passwd', 'C:/private', '.hidden/file', 'a\\b', 'out']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    module.check_state(state(name), folder)


if __name__ == '__main__':
    unittest.main()
