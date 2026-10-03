"""Research workflow boundaries and real reviewed execution on synthetic data."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workflow_project_server.py"
SPEC = importlib.util.spec_from_file_location("workflow_project_server", SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

CONTRACT = {"schema_version": 1, "engine": "typst",
            "fonts": {"body": "SimSun", "heading": "SimHei", "latin": "Times New Roman"},
            "body_size_pt": 12, "margins_cm": 2.5, "figure_width_mm": 160,
            "minimum_dpi": 300, "minimum_pages": 21}
SOLVER = '''import csv, json, os
from pathlib import Path
from helper import average
source = Path(os.environ["NE_SOURCE_INPUTS"]) / "data" / "observations.csv"
with source.open(encoding="utf-8") as stream:
    values = [float(row["value"]) for row in csv.DictReader(stream)]
output = Path("results")
output.mkdir(exist_ok=True)
(output / "metrics.json").write_text(json.dumps({"count": len(values), "mean": average(values)}), encoding="utf-8")
print("complete", len(values))
'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "user-case"
        self.inputs = self.root / "source-inputs"
        self.project = self.root / "skill"
        self.approvals = self.root / "host" / "approvals.json"
        self.workspace.mkdir()
        (self.inputs / "data").mkdir(parents=True)
        (self.inputs / "data/observations.csv").write_text("id,value\na,2\nb,5\nc,8\n", encoding="utf-8")
        (self.inputs / "statement.txt").write_text("Synthetic task: calculate the mean.\n", encoding="utf-8")
        (self.inputs / "original.bin").write_bytes(b"\x00original")
        (self.project / "references").mkdir(parents=True)
        (self.project / "SKILL.md").write_text("Project stage rules", encoding="utf-8")
        (self.project / "references/rendering-contract.md").write_text("Select actual template and fonts", encoding="utf-8")
        self.approvals.parent.mkdir()
        self.compiler = self.root / "compiler.exe"
        self.compiler.write_text("host-selected executable", encoding="utf-8")
        self.font_dir = self.root / "fonts"
        self.font_dir.mkdir()
        (self.workspace / "main.typ").write_text("= Initial manuscript\n", encoding="utf-8")
        (self.workspace / "rendering-contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.server = self.new_server()

    def new_server(self):
        return m.WorkflowServer(self.workspace, self.inputs, Path(sys.executable), self.compiler,
                                self.approvals, self.font_dir, project_root=self.project)

    def result(self, name, arguments=None):
        return self.server.call_tool(name, arguments or {})["structuredContent"]

    def write_code(self, content=SOLVER):
        self.assertTrue(self.result("write_artifact", {"path": "code/solver.py", "content": content})["written"])
        self.assertTrue(self.result("write_artifact", {"path": "code/helper.py", "content": "def average(values):\n    return sum(values) / len(values)\n"})["written"])
        return self.result("request_solver_execution", {"path": "code/solver.py"})

    def approve(self, request, approved=True):
        entry = {key: request[key] for key in ("path", "sha256", "code_tree_hash")}
        entry["approved"] = approved
        self.approvals.write_text(json.dumps({"schema_version": 1, "approvals": [entry]}), encoding="utf-8")

    def test_handshake_and_all_tools_advertised(self):
        response = self.server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["result"]["serverInfo"]["name"], "mathmodel-workflow-project")
        listing = self.server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {item["name"] for item in listing["result"]["tools"]}
        self.assertEqual(names, {item[0] for item in m.TOOL_DEFINITIONS})
        self.assertIn("not an OS sandbox", response["result"]["instructions"])

    def test_parent_project_and_workspace_reads_preserved(self):
        self.assertEqual(self.result("read_project_file", {"path": "SKILL.md"})["content"], "Project stage rules")
        self.assertIn("Initial manuscript", self.result("read_workspace_file", {"path": "main.typ"})["content"])
        self.write_code()
        self.assertEqual(self.result("read_workspace_file", {"path": "code/solver.py"})["content"], SOLVER)

    def test_input_inventory_pagination_and_prefix(self):
        first = self.result("list_inputs", {"max_items": 1})
        self.assertEqual(first["total_items"], 3)
        self.assertTrue(first["truncated"])
        second = self.result("list_inputs", {"start": first["next_start"], "max_items": 100})
        self.assertEqual(len(second["inputs"]), 2)
        selected = self.result("list_inputs", {"path_prefix": "data"})
        self.assertEqual([item["path"] for item in selected["inputs"]], ["data/observations.csv"])
        self.assertEqual(selected["inputs"][0]["sha256"], m.digest(self.inputs / "data/observations.csv"))

    def test_input_read_explicit_partial_range_and_full_file_hash(self):
        first = self.result("read_input_file", {"path": "data/observations.csv", "max_lines": 2})
        second = self.result("read_input_file", {"path": "data/observations.csv", "start_line": first["next_start_line"], "max_lines": 2})
        self.assertEqual(first["content"] + second["content"], (self.inputs / "data/observations.csv").read_bytes().decode("utf-8"))
        self.assertEqual(first["total_lines"], 4)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertNotEqual(first["returned_content_sha256"], first["sha256"])

    def test_large_text_window_uses_correct_sparse_line_offsets(self):
        large = self.inputs / "large.csv"
        large.write_text("".join(f"{index},中文字\n" for index in range(2505)), encoding="utf-8")
        # Host creates a new independent interface instance before freezing.
        self.server.frozen_inputs = self.server._input_snapshot()
        result = self.result("read_input_file", {"path": "large.csv", "start_line": 1999, "max_lines": 5})
        self.assertEqual(result["content"], b"".join(large.read_bytes().splitlines(keepends=True)[1998:2003]).decode("utf-8"))
        self.assertEqual(result["total_lines"], 2505)

    def test_empty_text_and_binary_refusal(self):
        empty = self.inputs / "empty.txt"
        empty.write_text("", encoding="utf-8")
        self.server.frozen_inputs = self.server._input_snapshot()
        self.assertEqual(self.result("read_input_file", {"path": "empty.txt"})["content"], "")
        self.assertFalse(self.result("read_input_file", {"path": "original.bin"})["passed"])

    def test_input_changed_after_startup_is_refused(self):
        (self.inputs / "statement.txt").write_text("Changed input", encoding="utf-8")
        self.assertFalse(self.result("read_input_file", {"path": "statement.txt"})["passed"])

    def test_only_frozen_inputs_and_relative_paths(self):
        (self.inputs / "later.txt").write_text("not frozen", encoding="utf-8")
        for path in ("later.txt", "../host/approvals.json", str(self.approvals), "statement.txt:stream", "/etc/passwd"):
            with self.subTest(path=path):
                self.assertFalse(self.result("read_input_file", {"path": path})["passed"])

    def test_private_input_tree_refused(self):
        (self.inputs / ".env").write_text("not public", encoding="utf-8")
        with self.assertRaises(m.ToolError):
            self.new_server()

    def test_input_hardlink_refused(self):
        os.link(self.inputs / "statement.txt", self.inputs / "alias.txt")
        with self.assertRaises(m.ToolError):
            self.new_server()

    def test_workspace_and_inputs_cannot_overlap(self):
        with self.assertRaises(m.ToolError):
            m.WorkflowServer(self.workspace, self.workspace, Path(sys.executable), self.compiler, self.approvals, project_root=self.project)

    def test_approval_file_cannot_be_model_writable_or_an_input(self):
        for path in (self.workspace / "approval.json", self.inputs / "approval.json", self.project / "approval.json"):
            with self.subTest(path=path), self.assertRaises(m.ToolError):
                m.WorkflowServer(self.workspace, self.inputs, Path(sys.executable), self.compiler, path, project_root=self.project)

    def test_write_allowed_artifacts_and_detect_real_revision(self):
        for path in ("code/a.py", "results/data.csv", "figures/flow.drawio", "paper/body.typ", "reports/analysis.md", "main.typ"):
            with self.subTest(path=path):
                result = self.result("write_artifact", {"path": path, "content": "first\n"})
                self.assertTrue(result["written"])
                revised = self.result("write_artifact", {"path": path, "content": "second\n"})
                self.assertEqual(revised["before_sha256"], result["sha256"])
                self.assertNotEqual(revised["sha256"], result["sha256"])
                for digest_value,expected in ((result['sha256'],b'first\n'),(revised['sha256'],b'second\n')):
                    snapshot=self.workspace/m.RUNTIME_ROOT/'artifact-history'/f'{digest_value}.txt'
                    self.assertEqual(snapshot.read_bytes(),expected)

    def test_tampered_artifact_history_cannot_be_silently_used(self):
        original=self.result('write_artifact',{'path':'code/a.py','content':'first\n'})
        history=self.workspace/m.RUNTIME_ROOT/'artifact-history'/f"{original['sha256']}.txt"
        history.write_text('tampered\n',encoding='utf-8')
        result=self.result('write_artifact',{'path':'code/a.py','content':'second\n'})
        self.assertFalse(result['passed'])
        self.assertEqual((self.workspace/'code/a.py').read_text(encoding='utf-8'),'first\n')

    def test_write_cannot_target_raw_accepted_pdf_private_or_service_paths(self):
        (self.workspace / "main.pdf").write_bytes(b"accepted PDF")
        for path in ("main.pdf", "original.txt", "inputs/a.csv", "../source-inputs/statement.txt", str(self.approvals),
                     "project-tool-events.jsonl", "asset-bindings.json", "reports/.env", "reports/credentials.json",
                     "reports/workflow-runtime/file.txt", ".workflow-runtime/server-state.json", "paper/raw.xlsx"):
            with self.subTest(path=path):
                self.assertFalse(self.result("write_artifact", {"path": path, "content": "replace"})["passed"])
        self.assertEqual((self.workspace / "main.pdf").read_bytes(), b"accepted PDF")

    def test_python_can_only_be_written_under_code(self):
        for path in ("reports/helper.py", "results/helper.py", "figures/helper.py", "paper/helper.py"):
            with self.subTest(path=path):
                self.assertFalse(self.result("write_artifact", {"path": path, "content": "print('no')"})["passed"])

    def test_write_refuses_hardlinked_targets(self):
        (self.workspace / "code").mkdir()
        os.link(self.inputs / "statement.txt", self.workspace / "code/linked.py")
        self.assertFalse(self.result("write_artifact", {"path": "code/linked.py", "content": "replace"})["passed"])
        self.assertIn("Synthetic task", (self.inputs / "statement.txt").read_text(encoding="utf-8"))

    def test_bounded_write_and_bad_parameter_types(self):
        for arguments in ({"path": "code/a.py", "content": "x" * (m.MAX_WRITE_BYTES + 1)},
                          {"path": "code/a.py", "content": "a\x00b"},
                          {"path": "code/a.py", "content": 3},
                          {"path": "code/a.py", "content": "pass", "shell": "run"}):
            self.assertFalse(self.result("write_artifact", arguments)["passed"])
        for arguments in ({"start": True}, {"max_items": 101}, {"start": -1}):
            self.assertFalse(self.result("list_inputs", arguments)["passed"])
        self.assertFalse(self.result("read_input_file", {"path": "statement.txt", "max_lines": 501})["passed"])

    def test_request_never_executes_and_exposes_bundle_hash_for_host(self):
        with patch.object(m.subprocess, "run", side_effect=AssertionError("must not execute")):
            request = self.write_code()
            pending = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertEqual(request["status"], "pending_review")
        self.assertFalse(request["execution_started"])
        self.assertEqual([item["path"] for item in request["code_files"]], ["code/helper.py", "code/solver.py"])
        self.assertEqual(pending["code_tree_hash"], request["code_tree_hash"])
        self.assertFalse(pending["execution_started"])
        self.assertNotIn(str(self.approvals), json.dumps(pending))

    def test_approved_bundle_runs_real_synthetic_computation(self):
        request = self.write_code()
        self.approve(request)
        before = {key: item["sha256"] for key, item in self.server.frozen_inputs.items()}
        result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["execution_started"])
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["inputs_preserved"])
        self.assertTrue(result["protected_outputs_preserved"])
        self.assertFalse(result["scientific_correctness_verified"])
        self.assertFalse(result["os_sandbox"])
        metrics = self.workspace / "results/metrics.json"
        self.assertEqual(json.loads(metrics.read_text(encoding="utf-8")), {"count": 3, "mean": 5.0})
        self.assertEqual(result["outputs"], [{"path": "results/metrics.json", "bytes": metrics.stat().st_size, "sha256": m.digest(metrics)}])
        self.assertEqual(before, {key: item["sha256"] for key, item in self.server._input_snapshot().items()})
        self.assertEqual(json.loads((self.workspace / result["run_record"]).read_text(encoding="utf-8"))["source_sha256"], request["sha256"])

    def test_changed_entry_requires_new_approval(self):
        request = self.write_code()
        self.approve(request)
        self.result("write_artifact", {"path": "code/solver.py", "content": SOLVER + "print('revision')\n"})
        with patch.object(m.subprocess, "run", side_effect=AssertionError("must not execute stale code")):
            result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertEqual(result["status"], "pending_review")

    def test_changed_helper_requires_new_approval(self):
        request = self.write_code()
        self.approve(request)
        self.result("write_artifact", {"path": "code/helper.py", "content": "def average(values):\n    return -1\n"})
        with patch.object(m.subprocess, "run", side_effect=AssertionError("must not execute stale helper")):
            result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertEqual(result["status"], "pending_review")
        self.assertEqual(result["sha256"], request["sha256"])
        self.assertNotEqual(result["code_tree_hash"], request["code_tree_hash"])

    def test_new_python_module_invalidates_old_bundle_approval(self):
        request = self.write_code()
        self.approve(request)
        self.result("write_artifact", {"path": "code/new.py", "content": "raise RuntimeError('new')\n"})
        self.assertEqual(self.result("run_approved_solver", {"path": "code/solver.py"})["status"], "pending_review")

    def test_python_cache_does_not_change_bundle_hash(self):
        request = self.write_code()
        (self.workspace / "code/__pycache__").mkdir()
        (self.workspace / "code/__pycache__/cache.py").write_text("unexecuted cache entry", encoding="utf-8")
        repeated = self.result("request_solver_execution", {"path": "code/solver.py"})
        self.assertEqual(repeated["code_tree_hash"], request["code_tree_hash"])

    def test_false_invalid_or_duplicate_approval_never_executes(self):
        request = self.write_code()
        self.approve(request, approved=False)
        self.assertFalse(self.result("run_approved_solver", {"path": "code/solver.py"})["execution_started"])
        self.approvals.write_text("invalid JSON", encoding="utf-8")
        self.assertFalse(self.result("run_approved_solver", {"path": "code/solver.py"})["passed"])
        self.approve(request)
        data = json.loads(self.approvals.read_text(encoding="utf-8"))
        data["approvals"].append(dict(data["approvals"][0]))
        self.approvals.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(self.result("run_approved_solver", {"path": "code/solver.py"})["passed"])

    def test_input_changes_before_execution_refuse_even_approved_code(self):
        request = self.write_code()
        self.approve(request)
        (self.inputs / "statement.txt").write_text("changed", encoding="utf-8")
        with patch.object(m.subprocess, "run", side_effect=AssertionError("must not execute changed input")):
            self.assertFalse(self.result("run_approved_solver", {"path": "code/solver.py"})["passed"])

    def test_child_environment_has_no_provider_keys_and_host_font_available(self):
        code = '''import os
print("HAS_PROVIDER", "MM_TEST_PROVIDER_KEY" in os.environ)
print("INPUT_PRESENT", "NE_SOURCE_INPUTS" in os.environ)
print("FONT_PRESENT", "MATHMODEL_CJK_FONT_DIR" in os.environ)
print("BACKEND", os.environ.get("MPLBACKEND"))
'''
        with patch.dict(os.environ, {"MM_TEST_PROVIDER_KEY": "never-forward-this-provider-value"}):
            self.server = self.new_server()
            request = self.write_code(code)
            self.approve(request)
            result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["passed"], result)
        self.assertIn("HAS_PROVIDER False", result["stdout_tail"])
        self.assertIn("INPUT_PRESENT True", result["stdout_tail"])
        self.assertIn("FONT_PRESENT True", result["stdout_tail"])
        self.assertIn("BACKEND Agg", result["stdout_tail"])
        self.assertNotIn("never-forward-this-provider-value", json.dumps(result))

    def test_timeout_and_nonzero_exit_are_not_success(self):
        request = self.write_code()
        self.approve(request)
        with patch.object(m.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixed", 180, output=b"partial", stderr=b"timeout")):
            timed_out = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertEqual(timed_out["status"], "timed_out")
        self.assertFalse(timed_out["passed"])
        request = self.write_code("raise RuntimeError('synthetic failure')\n")
        self.approve(request)
        failed = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertFalse(failed["passed"])
        self.assertNotEqual(failed["exit_code"], 0)
        self.assertIn("synthetic failure", failed["stderr_tail"])

    def test_restart_preserves_input_baseline_and_approval_execution(self):
        request = self.write_code()
        self.approve(request)
        self.server = self.new_server()
        self.assertTrue(self.result("run_approved_solver", {"path": "code/solver.py"})["passed"])
        (self.inputs / "statement.txt").write_text("changed between sessions", encoding="utf-8")
        with self.assertRaises(m.ToolError):
            self.new_server()

    def test_solver_mutation_is_detected_not_mislabeled_as_sandboxing(self):
        code = '''import os
from pathlib import Path
(Path(os.environ["NE_SOURCE_INPUTS"]) / "statement.txt").write_text("changed by reviewed fixture", encoding="utf-8")
'''
        request = self.write_code(code)
        self.approve(request)
        result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["execution_started"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["inputs_preserved"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["os_sandbox"])

    def test_accepted_pdf_changed_by_reviewed_code_fails_integrity_check(self):
        (self.workspace / "main.pdf").write_bytes(b"host accepted PDF")
        request = self.write_code("from pathlib import Path\nPath('main.pdf').write_bytes(b'changed')\n")
        self.approve(request)
        result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["execution_started"])
        self.assertFalse(result["protected_outputs_preserved"])
        self.assertFalse(result["passed"])

    def test_two_real_solver_runs_keep_recoverable_old_and_new_csv_bytes(self):
        old = b'id,value\na,2\n'
        new = b'id,value\na,9\n'
        def script(payload):
            return 'from pathlib import Path\nPath("results").mkdir(exist_ok=True)\nPath("results/table.csv").write_bytes(' + repr(payload) + ')\n'
        request = self.write_code(script(old))
        self.approve(request)
        first = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(first['passed'])
        self.assertTrue(first['output_history_complete'])
        self.assertEqual(first['output_changes'][0]['classification'], 'created')
        old_receipt = first['output_history']['after']['files'][0]
        self.assertEqual((self.workspace / old_receipt['snapshot_path']).read_bytes(), old)
        request = self.write_code(script(new))
        self.approve(request)
        second = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(second['passed'])
        self.assertEqual(second['output_changes'][0]['classification'], 'modified')
        before, after = second['output_changes'][0]['before'], second['output_changes'][0]['after']
        self.assertEqual(before['snapshot_path'], old_receipt['snapshot_path'])
        self.assertEqual((self.workspace / before['snapshot_path']).read_bytes(), old)
        self.assertEqual((self.workspace / after['snapshot_path']).read_bytes(), new)
        self.assertEqual((self.workspace / 'results/table.csv').read_bytes(), new)
        for receipt in (old_receipt, before, after):
            self.assertEqual(m.digest(self.workspace / receipt['snapshot_path']), receipt['sha256'])
        run_record = json.loads((self.workspace / second['run_record']).read_text(encoding='utf-8'))
        self.assertTrue(run_record['output_history_complete'])
        self.assertEqual(run_record['output_history'], second['output_history'])

    def test_unchanged_outputs_reuse_blob_and_are_not_newly_generated(self):
        request = self.write_code()
        self.approve(request)
        first = self.result('run_approved_solver', {'path': 'code/solver.py'})
        receipt = first['output_history']['after']['files'][0]
        blob = self.workspace / receipt['snapshot_path']
        timestamp = blob.stat().st_mtime_ns
        second = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(second['passed'])
        change = second['output_changes'][0]
        self.assertEqual(change['classification'], 'unchanged')
        self.assertFalse(change['changed_this_run'])
        self.assertEqual(change['before']['snapshot_path'], change['after']['snapshot_path'])
        self.assertEqual(blob.stat().st_mtime_ns, timestamp)
        self.assertEqual(len(list((self.server.runtime / 'output-history').glob('*.bin'))), 1)

    def test_noop_solver_does_not_claim_preexisting_results_as_created(self):
        (self.workspace / 'results').mkdir()
        (self.workspace / 'results/old.csv').write_bytes(b'preserved\n')
        request = self.write_code('print("No derived outputs produced")\n')
        self.approve(request)
        result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['passed'])
        self.assertEqual(result['output_changes'][0]['classification'], 'unchanged')
        self.assertFalse(result['output_changes'][0]['changed_this_run'])
        self.assertFalse(result['scientific_correctness_verified'])

    def test_change_inventory_tracks_created_modified_unchanged_and_deleted(self):
        (self.workspace / 'results').mkdir()
        for name in ('keep', 'replace', 'remove'):
            (self.workspace / f'results/{name}.csv').write_bytes(name.encode())
        request = self.write_code('''from pathlib import Path
Path("results/replace.csv").write_bytes(b"new bytes")
Path("results/remove.csv").unlink()
Path("results/create.csv").write_bytes(b"new file")
''')
        self.approve(request)
        result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['passed'])
        changes = {item['path']: item for item in result['output_changes']}
        self.assertEqual({name: item['classification'] for name, item in changes.items()},
                         {'results/create.csv': 'created', 'results/replace.csv': 'modified',
                          'results/keep.csv': 'unchanged', 'results/remove.csv': 'deleted'})
        removed = changes['results/remove.csv']
        self.assertIsNone(removed['after'])
        self.assertEqual((self.workspace / removed['before']['snapshot_path']).read_bytes(), b'remove')

    def test_same_binary_content_in_two_output_paths_is_deduplicated(self):
        request = self.write_code('''from pathlib import Path
Path("figures").mkdir()
Path("results").mkdir()
Path("figures/a.bin").write_bytes(b"\\x00\\xffbinary")
Path("results/b.bin").write_bytes(b"\\x00\\xffbinary")
''')
        self.approve(request)
        result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['passed'])
        receipts = result['output_history']['after']['files']
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0]['snapshot_path'], receipts[1]['snapshot_path'])
        self.assertEqual((self.workspace / receipts[0]['snapshot_path']).read_bytes(), b'\x00\xffbinary')

    def test_preexisting_output_over_file_budget_refuses_execution(self):
        (self.workspace / 'results').mkdir()
        (self.workspace / 'results/large.csv').write_bytes(b'123456')
        request = self.write_code()
        self.approve(request)
        with patch.object(m, 'MAX_OUTPUT_FILE_BYTES', 5), patch.object(m.subprocess, 'run', side_effect=AssertionError('must not run')):
            result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertFalse(result['execution_started'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['output_history_complete'])
        self.assertIn('per-file', result['output_history_errors'][0])
        self.assertEqual((self.workspace / 'results/large.csv').read_bytes(), b'123456')

    def test_postrun_output_over_file_budget_fails_without_truncation(self):
        request = self.write_code('from pathlib import Path\nPath("results").mkdir()\nPath("results/large.bin").write_bytes(b"123456")\n')
        self.approve(request)
        with patch.object(m, 'MAX_OUTPUT_FILE_BYTES', 5):
            result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['execution_started'])
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['passed'])
        self.assertFalse(result['output_history_complete'])
        self.assertIsNone(result['output_changes'])
        self.assertEqual((self.workspace / 'results/large.bin').read_bytes(), b'123456')
        self.assertEqual(result['output_snapshot_budget']['per_file_bytes'], 5)

    def test_round_budget_counts_before_and_after_even_when_blob_reused(self):
        (self.workspace / 'results').mkdir()
        (self.workspace / 'results/existing.bin').write_bytes(b'12345')
        request = self.write_code('print("leave outputs untouched")\n')
        self.approve(request)
        with patch.object(m, 'MAX_OUTPUT_ROUND_BYTES', 8):
            result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['execution_started'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['output_history_complete'])
        self.assertEqual(result['output_history']['before']['bytes'], 5)
        self.assertIsNone(result['output_history']['after'])
        self.assertEqual(result['output_snapshot_budget']['before_plus_after_bytes'], 8)
        before = result['output_history']['before']['files'][0]
        self.assertEqual((self.workspace / before['snapshot_path']).read_bytes(), b'12345')

    def test_preexisting_output_count_over_budget_refuses_execution(self):
        (self.workspace / 'results').mkdir()
        for name in ('one', 'two'):
            (self.workspace / f'results/{name}.txt').write_text(name)
        request = self.write_code()
        self.approve(request)
        with patch.object(m, 'MAX_OUTPUT_FILES_PER_STAGE', 1), patch.object(m.subprocess, 'run', side_effect=AssertionError('must not run')):
            result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertFalse(result['execution_started'])
        self.assertIn('file count', result['output_history_errors'][0])

    def test_corrupted_retained_blob_is_refused_before_execution(self):
        request = self.write_code()
        self.approve(request)
        first = self.result('run_approved_solver', {'path': 'code/solver.py'})
        blob = self.workspace / first['output_history']['after']['files'][0]['snapshot_path']
        blob.write_bytes(b'corrupted previous version')
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('must not run')):
            second = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertFalse(second['execution_started'])
        self.assertFalse(second['output_history_complete'])
        self.assertEqual(blob.read_bytes(), b'corrupted previous version')
        self.assertIn('history snapshot changed', second['output_history_errors'][0])

    def test_solver_mutation_of_before_blob_is_detected(self):
        (self.workspace / 'results').mkdir()
        original = self.workspace / 'results/old.csv'
        original.write_bytes(b'old')
        expected_hash = m.digest(original)
        code = ('from pathlib import Path\n'
                'Path(".workflow-runtime/output-history/' + expected_hash + '.bin").write_bytes(b"corrupt")\n'
                'Path("results/old.csv").write_bytes(b"new")\n')
        request = self.write_code(code)
        self.approve(request)
        result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertTrue(result['execution_started'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['output_history_complete'])
        self.assertIn('SHA-256', result['output_history_errors'][0])

    def test_hardlinked_preexisting_output_refuses_execution(self):
        (self.workspace / 'results').mkdir()
        original = self.root / 'outside.bin'
        original.write_bytes(b'outside immutable bytes')
        os.link(original, self.workspace / 'results/alias.bin')
        request = self.write_code()
        self.approve(request)
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('must not run')):
            result = self.result('run_approved_solver', {'path': 'code/solver.py'})
        self.assertFalse(result['execution_started'])
        self.assertFalse(result['output_history_complete'])
        self.assertIn('Hard-linked', result['output_history_errors'][0])
        self.assertEqual(original.read_bytes(), b'outside immutable bytes')

    def test_bundle_changed_during_execution_fails_current_version_acceptance(self):
        request = self.write_code("from pathlib import Path\nPath('code/helper.py').write_text('changed by run', encoding='utf-8')\n")
        self.approve(request)
        result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["execution_started"])
        self.assertFalse(result["code_bundle_preserved"])
        self.assertFalse(result["passed"])
        self.assertEqual(self.result("run_approved_solver", {"path": "code/solver.py"})["status"], "pending_review")

    def test_read_audit_has_ranges_hashes_but_no_data_or_source_text(self):
        result = self.result("read_input_file", {"path": "statement.txt", "max_lines": 1})
        records = [json.loads(line) for line in (self.workspace / "project-tool-events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["result_summary"]["returned_range"], result["returned_range"])
        self.assertEqual(records[-1]["result_summary"]["sha256"], result["sha256"])
        self.assertNotIn("Synthetic task", json.dumps(records))

    def test_malicious_hardlinked_output_cannot_pass_inventory(self):
        request = self.write_code('''import os
from pathlib import Path
Path("results").mkdir(exist_ok=True)
os.link(Path(os.environ["NE_SOURCE_INPUTS"]) / "statement.txt", "results/alias.txt")
''')
        self.approve(request)
        result = self.result("run_approved_solver", {"path": "code/solver.py"})
        self.assertTrue(result["execution_started"])
        self.assertFalse(result["passed"])
        self.assertTrue(result["output_inventory_errors"])

    def test_solver_cannot_be_approved_with_arbitrary_args(self):
        self.write_code()
        for name in ("request_solver_execution", "run_approved_solver"):
            result = self.result(name, {"path": "code/solver.py", "args": ["--shell"]})
            self.assertFalse(result["passed"])

    def test_real_stdio_cli_and_unauthorized_run(self):
        request = self.write_code()
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_approved_solver", "arguments": {"path": "code/solver.py"}}},
        ]
        command = [sys.executable, "-X", "utf8", str(SCRIPT), "--workspace", str(self.workspace),
                   "--inputs", str(self.inputs), "--python", sys.executable, "--compiler", str(self.compiler),
                   "--approvals", str(self.approvals)]
        # CLI uses its own real repository root but the independent fixture workspace.
        process = subprocess.run(command, input="".join(json.dumps(item) + "\n" for item in lines),
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        result = responses[-1]["result"]["structuredContent"]
        self.assertEqual(result["code_tree_hash"], request["code_tree_hash"])
        self.assertFalse(result["execution_started"])


if __name__ == "__main__":
    unittest.main()
