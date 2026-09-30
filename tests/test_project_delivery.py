import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_project_delivery", ROOT/"scripts/check_project_delivery.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ProjectDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = self.root/"delivery.json"
        self.data = {"schema_version": 1, "mode": "full-delivery",
                     "deliverables": [{"id": "paper", "path": "out/paper.pdf", "required": True}],
                     "questions": [{"id": "Q1", "solver": "code/q1.py", "results": ["results/q1.csv"],
                                    "run_command": "python code/q1.py"}]}
        for name, body in [("out/paper.pdf", b"synthetic file inventory"),
                           ("code/q1.py", b"print('synthetic')"), ("results/q1.csv", b"x,y\n1,2\n")]:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")
        return self.manifest

    def test_full_delivery_inventory_without_original_appendix(self):
        result, _ = CHECKER.check(self.save(), self.root)
        self.assertTrue(result["inventory_complete"])
        self.assertFalse(result["questions"][0]["run_command_executed_by_checker"])
        self.assertNotIn("passed", result)
        self.assertEqual(result["deliverables"][0]["sha256"],
                         hashlib.sha256((self.root/"out/paper.pdf").read_bytes()).hexdigest())

    def test_missing_solver_result_and_empty_required_output_fail(self):
        (self.root/"code/q1.py").unlink()
        (self.root/"results/q1.csv").unlink()
        (self.root/"out/paper.pdf").write_bytes(b"")
        result, _ = CHECKER.check(self.save(), self.root)
        self.assertFalse(result["inventory_complete"])
        self.assertEqual(len(result["failures"]), 3)

    def test_optional_output_can_be_absent_and_small_revision_needs_no_solver(self):
        self.data["mode"] = "layout-only"
        self.data["questions"] = []
        self.data["deliverables"].append({"id": "word", "path": "out/paper.docx", "required": False})
        result, _ = CHECKER.check(self.save(), self.root)
        self.assertTrue(result["inventory_complete"])
        self.assertEqual(result["required_deliverables"], 1)
        self.assertFalse(result["deliverables"][1]["present"])

    def test_preserved_input_change_is_detected(self):
        source = self.root/"source.pdf"
        source.write_bytes(b"user appendix baseline")
        self.data["preserved_inputs"] = [{"path": "source.pdf", "sha256": CHECKER.file_hash(source)}]
        self.assertTrue(CHECKER.check(self.save(), self.root)[0]["inventory_complete"])
        source.write_bytes(b"modified appendix")
        result, _ = CHECKER.check(self.manifest, self.root)
        self.assertFalse(result["inventory_complete"])
        self.assertIn("content changed from baseline", result["failures"][0])

    def test_unsafe_paths_and_duplicate_outputs_are_rejected(self):
        for path in ["../outside.pdf", "/absolute.pdf", "C:/private.pdf"]:
            with self.subTest(path=path):
                self.data["deliverables"][0]["path"] = path
                with self.assertRaises(ValueError):
                    CHECKER.check(self.save(), self.root)
        self.data["deliverables"][0]["path"] = "out/paper.pdf"
        self.data["deliverables"].append({"id": "duplicate", "path": "OUT/PAPER.PDF"})
        with self.assertRaisesRegex(ValueError, "case-colliding"):
            CHECKER.check(self.save(), self.root)

    def test_existing_report_and_declared_input_are_not_overwritten(self):
        self.save()
        before = self.manifest.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECKER.main([str(self.manifest), "--project-root", str(self.root),
                                           "--report", "delivery.json"]), 2)
        self.assertEqual(self.manifest.read_bytes(), before)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(CHECKER.main([str(self.manifest), "--project-root", str(self.root),
                                           "--report", "qa/inventory.json"]), 0)
        report_before = (self.root/"qa/inventory.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CHECKER.main([str(self.manifest), "--project-root", str(self.root),
                                           "--report", "qa/inventory.json"]), 2)
        self.assertEqual((self.root/"qa/inventory.json").read_bytes(), report_before)

    def test_run_command_is_only_recorded_and_not_executed(self):
        sentinel = self.root/"unexpected.txt"
        self.data["questions"][0]["run_command"] = "create unexpected.txt with PRIVATE-VALUE"
        self.save()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(CHECKER.main([str(self.manifest), "--project-root", str(self.root),
                                           "--report", "qa/inventory.json"]), 0)
        self.assertFalse(sentinel.exists())
        self.assertNotIn("PRIVATE-VALUE", output.getvalue())
        self.assertNotIn("PRIVATE-VALUE", (self.root/"qa/inventory.json").read_text(encoding="utf-8"))

    def test_full_delivery_cannot_silently_omit_question_list(self):
        self.data["questions"] = []
        with self.assertRaisesRegex(ValueError, "actual question list"):
            CHECKER.check(self.save(), self.root)


if __name__ == "__main__":
    unittest.main()
