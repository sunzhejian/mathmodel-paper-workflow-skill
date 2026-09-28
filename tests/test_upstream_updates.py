import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_upstream_updates.py"
SPEC = importlib.util.spec_from_file_location("check_upstream_updates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpstreamUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "examples").mkdir()
        (self.root / "examples/upstream-lock.json").write_text(json.dumps({"sources": [
            {"name": "Example", "url": "https://example.org/project", "commit": "abc123"}
        ]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_changed_remote_is_reported_without_mutation(self):
        response = type("Result", (), {"returncode": 0, "stdout": "def456\tHEAD\n", "stderr": ""})()
        with patch.object(MODULE.subprocess, "run", return_value=response) as run:
            result = MODULE.inspect(self.root)
        self.assertEqual(result["updates"], 1)
        self.assertEqual(result["sources"][0]["status"], "update_available")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][:2], ["git", "ls-remote"])

    def test_network_failure_is_not_treated_as_no_update(self):
        response = type("Result", (), {"returncode": 128, "stdout": "", "stderr": "network unavailable"})()
        with patch.object(MODULE.subprocess, "run", return_value=response):
            result = MODULE.inspect(self.root)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["sources"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
