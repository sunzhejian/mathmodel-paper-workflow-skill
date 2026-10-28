from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which("node"), "Node.js required for portable replay checks")
class ContestReplayTests(unittest.TestCase):
    def test_preserved_aliases_outputs_and_fail_closed_verification(self):
        result = subprocess.run(["node", "--test", "tests/contest_replay_cases.mjs"],
                                cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass 7", result.stdout)
