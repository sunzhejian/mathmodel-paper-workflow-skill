"""Optional research MCP for model-written artifacts and host-reviewed execution.

The host selects a separate workspace, immutable input tree, fixed Python and
Typst executables, and a private approval file. This is NOT an OS sandbox: a
host must review the Python entry and entire code bundle before approving their hashes.
Only that reviewed Python bundle snapshot runs, with no arbitrary shell or model arguments.
Existing paper rendering tools remain available through ProjectServer.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import paper_project_server as paper

ToolError = paper.ToolError
PROJECT_ROOT = SCRIPT_DIR.parent
MAX_WRITE_BYTES = 512 * 1024
MAX_WINDOW_BYTES = 512 * 1024
MAX_OUTPUT_FILE_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_ROUND_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_FILES_PER_STAGE = 4096
SOLVER_TIMEOUT = 180
ARTIFACT_ROOTS = {"code", "results", "figures", "paper", "reports"}
ROOT_ARTIFACTS = {"main.typ", "rendering-contract.json"}
TEXT_SUFFIXES = paper.TEXT_SUFFIXES | {".py"}
RESERVED_PARTS = {".workflow-runtime", "workflow-runtime", "workflow-requests.jsonl"}
RUNTIME_ROOT = ".workflow-runtime"
SOLVER_LAUNCHER = ("import runpy,sys;sys.path.insert(0,sys.argv[1]);"
                   "sys.path.insert(0,sys.argv[2]);"
                   "runpy.run_path(sys.argv[3],run_name='__main__')")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def optional_schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {},
            "required": list(required), "additionalProperties": False}


NEW_TOOLS = [
    ("list_inputs", "List frozen host-provided inputs, with hashes and explicit pagination. Data are input files, not reference answers. No original is mutated.",
     optional_schema({"path_prefix": {"type": "string"}, "start": {"type": "integer", "minimum": 0},
                      "max_items": {"type": "integer", "minimum": 1, "maximum": 100}}), True),
    ("read_input_file", "Read selected physical lines of one frozen UTF-8 input projection. Defaults to 160 lines, max 500; follow next_start_line. Whole-file SHA never proves all data were read. Binary originals require their reader, not text guessing.", paper.read_schema(), True),
    ("write_artifact", "Write model-authored UTF-8 text under code/results/figures/paper/reports, or main.typ/rendering-contract.json. Never overwrite original inputs, PDFs, private files or service logs. This does not approve execution.",
     paper.input_schema(path={"type": "string"}, content={"type": "string"}), False),
    ("request_solver_execution", "Record entry source SHA, the complete code/**/*.py bundle hash and file list for host review. This tool NEVER executes code or approves it. Any changed Python module requires a new host approval.",
     paper.input_schema(path={"type": "string"}), False),
    ("run_approved_solver", "Execute only the exact entry SHA and complete Python bundle hash independently approved by the host. Uses fixed Python, no shell, no arbitrary arguments, clean environment, 180s timeout and workspace cwd. Missing approval returns pending_review, without execution. This is not an OS sandbox or scientific validation.",
     paper.input_schema(path={"type": "string"}), False),
]
TOOL_DEFINITIONS = paper.TOOL_DEFINITIONS + NEW_TOOLS


class WorkflowServer(paper.ProjectServer):
    def __init__(self, workspace, inputs, python, compiler, approvals, font_dir=None,
                 drawio=None, *, project_root=PROJECT_ROOT):
        super().__init__(workspace, compiler, font_dir, drawio, project_root=project_root)
        self.inputs = self._real_directory(inputs, "--inputs")
        if (self.inputs == self.workspace or self.inputs.is_relative_to(self.workspace)
                or self.workspace.is_relative_to(self.inputs)):
            raise ToolError("Inputs and workspace must be separate non-overlapping directories")
        if self.inputs == self.project_root or self.inputs.is_relative_to(self.project_root):
            raise ToolError("Real inputs must stay outside the skill distribution")
        self.python = Path(python).resolve(strict=True)
        if not self.python.is_file():
            raise ToolError("Host-selected Python must be an existing executable file")
        approval = Path(approvals).absolute()
        if not approval.parent.is_dir() or paper._is_link(approval.parent):
            raise ToolError("Host approval file needs an existing real parent directory")
        self.approvals = paper.confined(approval.parent.resolve(), approval.name,
                                       existing=False, private=False)
        if (self.approvals.is_relative_to(self.workspace)
                or self.approvals.is_relative_to(self.inputs)
                or self.approvals.is_relative_to(self.project_root)):
            raise ToolError("Host approval file must stay outside model-write, input and skill roots")
        self.frozen_inputs = self._input_snapshot()
        if not self.frozen_inputs:
            raise ToolError("Host-provided input tree must contain at least one original or projection")
        self.line_indexes = {}
        self.protected_paths = {"main.pdf", "asset-bindings.json", "project-tool-events.jsonl"}
        self.runtime = self.workspace / RUNTIME_ROOT
        state = self.runtime / "server-state.json"
        if self.runtime.exists():
            if not self.runtime.is_dir() or paper._is_link(self.runtime) or not state.is_file():
                raise ToolError("Existing runtime directory is not a reviewed workflow service directory")
            paper.confined(self.workspace, f"{RUNTIME_ROOT}/server-state.json")
            recorded = json.loads(state.read_text(encoding="utf-8"))
            if (not isinstance(recorded, dict) or recorded.get("schema_version") != 1
                    or recorded.get("frozen_inputs") != self.frozen_inputs):
                raise ToolError("Input inventory differs from the initial service state; original inputs must stay frozen")
        else:
            self.runtime.mkdir()
            state.write_text(json.dumps({"schema_version": 1, "frozen_inputs": self.frozen_inputs},
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _real_directory(value, label):
        target = Path(value).absolute()
        if not target.is_dir() or paper._is_link(target):
            raise ToolError(label + " must be an existing real directory")
        return target.resolve()

    def sanitize(self, text):
        text = super().sanitize(text)
        if hasattr(self, "approvals"):
            text = text.replace(str(self.approvals), "[host approval]")
            text = text.replace(self.approvals.as_posix(), "[host approval]")
        return text

    def _input_snapshot(self):
        record = {}
        for current, directories, files in os.walk(self.inputs, followlinks=False):
            parent = Path(current)
            for name in directories:
                target = parent / name
                parts = target.relative_to(self.inputs).parts
                if paper._is_link(target) or paper.private_path(parts):
                    raise ToolError("Private or linked directory cannot be an input source")
            for name in files:
                relative = (parent / name).relative_to(self.inputs).as_posix()
                target = paper.confined(self.inputs, relative)
                if not stat.S_ISREG(target.stat().st_mode):
                    raise ToolError("Input sources must be ordinary files")
                record[relative] = {"path": relative, "bytes": target.stat().st_size,
                                    "sha256": digest(target),
                                    "text_supported": target.suffix.lower() in TEXT_SUFFIXES}
        return record

    def _input_file(self, path):
        parts = paper.relative_parts(path)
        key = "/".join(parts)
        if key not in self.frozen_inputs:
            raise ToolError("File is not in the host-frozen input inventory")
        target = paper.confined(self.inputs, key)
        expected = self.frozen_inputs[key]
        if target.stat().st_size != expected["bytes"] or digest(target) != expected["sha256"]:
            raise ToolError("Input changed after startup; original/projection must be reviewed again")
        return key, target

    def list_inputs(self, path_prefix="", start=0, max_items=100):
        if type(start) is not int or start < 0 or type(max_items) is not int or not 1 <= max_items <= 100:
            raise ToolError("Input pagination requires start >= 0 and max_items in 1..100")
        prefix = "/".join(paper.relative_parts(path_prefix)) if path_prefix else ""
        items = [self.frozen_inputs[key] for key in sorted(self.frozen_inputs)
                 if not prefix or key == prefix or key.startswith(prefix + "/")]
        if start > len(items):
            raise ToolError("start is beyond the selected inventory")
        selected = items[start:start + max_items]
        end = start + len(selected)
        return {"inputs": selected, "total_items": len(items), "returned_range": [start, end],
                "truncated": end < len(items), "next_start": end if end < len(items) else None,
                "scope": "Frozen inventory, not parsing, formula correctness, understanding or full data processing"}

    def _text_index(self, key, target):
        if key not in self.line_indexes:
            blocks, total, position = [], 0, 0
            with target.open("rb") as stream:
                for line in stream:
                    if total % 1000 == 0:
                        blocks.append((total, position))
                    total += 1
                    position += len(line)
            self.line_indexes[key] = (blocks, total)
        return self.line_indexes[key]

    def read_input_file(self, path, start_line=1, max_lines=160):
        if type(start_line) is not int or start_line < 1 or type(max_lines) is not int or not 1 <= max_lines <= 500:
            raise ToolError("start_line must be positive and max_lines an integer in 1..500")
        key, target = self._input_file(path)
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise ToolError("Binary original has no text projection; use the appropriate host reader")
        blocks, total = self._text_index(key, target)
        if start_line > max(1, total):
            raise ToolError("start_line is beyond this file")
        selected, byte_count = [], 0
        index = bisect_right([item[0] for item in blocks], start_line - 1) - 1
        first, offset = blocks[max(index, 0)] if blocks else (0, 0)
        with target.open("rb") as stream:
            stream.seek(offset)
            for physical_line, raw in enumerate(stream, first + 1):
                if physical_line < start_line:
                    continue
                byte_count += len(raw)
                if byte_count > MAX_WINDOW_BYTES:
                    raise ToolError("Selected line window exceeds 512 KiB; request fewer lines")
                selected.append(raw)
                if len(selected) >= max_lines:
                    break
        try:
            content = b"".join(selected).decode("utf-8-sig" if start_line == 1 else "utf-8")
        except UnicodeError as exc:
            raise ToolError("Input projection is not UTF-8; no encoding is guessed") from exc
        if "\x00" in content:
            raise ToolError("Binary content cannot be supplied as text")
        if self.sanitize(content) != content:
            raise ToolError("Credential-like input content cannot be returned")
        end = start_line + len(selected) - 1
        return {"path": key, "content": content, "sha256": self.frozen_inputs[key]["sha256"],
                "returned_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "returned_range": [start_line, end], "total_lines": total,
                "truncated": start_line > 1 or end < total,
                "next_start_line": end + 1 if end < total else None,
                "scope": "Returned physical UTF-8 lines only; file hash is not full-read evidence"}

    def read(self, path):
        if path.suffix.lower() == ".py":
            if path.stat().st_size > paper.MAX_TEXT_BYTES:
                raise ToolError("Workspace code exceeds the 4 MiB text read limit")
            text = path.read_text(encoding="utf-8-sig")
            if "\x00" in text:
                raise ToolError("Workspace source is not ordinary UTF-8 text")
            return text
        return super().read(path)

    def _artifact(self, path, existing=False):
        parts = paper.relative_parts(path)
        key = "/".join(parts)
        if (key not in ROOT_ARTIFACTS and parts[0] not in ARTIFACT_ROOTS
                or key in self.protected_paths or any(part in RESERVED_PARTS for part in parts)):
            raise ToolError("Write only model artifacts; originals, accepted PDFs and service files are protected")
        target = paper.confined(self.workspace, key, existing=existing)
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise ToolError("write_artifact accepts supported UTF-8 source/data text, not binary originals or PDF outputs")
        if target.suffix.lower() == ".py" and parts[0] != "code":
            raise ToolError("Python artifacts can only be written under code/")
        if target.exists() and not target.is_file():
            raise ToolError("Artifact destination must be a regular file")
        return key, target

    def write_artifact(self, path, content):
        key, target = self._artifact(path)
        if not isinstance(content, str) or "\x00" in content or len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ToolError("Artifact content must be UTF-8 text of at most 512 KiB")
        if self.sanitize(content) != content:
            raise ToolError("Credential-like content cannot be written into model artifacts")
        before = digest(target) if target.exists() else None
        data = content.encode("utf-8")
        history_dir = self.runtime / 'artifact-history'
        history_dir.mkdir(exist_ok=True)
        if paper._is_link(history_dir):
            raise ToolError('Artifact history cannot be a linked directory')
        snapshots = [(hashlib.sha256(data).hexdigest(), data)]
        if target.exists():
            snapshots.append((before, target.read_bytes()))
        for digest_value, snapshot in snapshots:
            history_path = paper.confined(self.workspace, f'{RUNTIME_ROOT}/artifact-history/{digest_value}.txt', existing=False)
            if history_path.exists():
                if digest(history_path) != digest_value:
                    raise ToolError('Artifact history content changed; preserve the original model versions')
            else:
                history_path.write_bytes(snapshot)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Resolve again after creating parents; never knowingly follow a changed link.
        paper.confined(self.workspace, key, existing=False)
        temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return {"path": key, "written": True, "bytes": len(data), "before_sha256": before,
                "sha256": digest(target), "changed": before != digest(target),
                "history_sha256": [item[0] for item in snapshots],
                "execution_approved": False, "scope": "Model-authored artifact; no execution or scientific acceptance"}

    def _solver(self, path):
        key, source = self._artifact(path, existing=True)
        if source.suffix.lower() != ".py" or not key.startswith("code/"):
            raise ToolError("Request one model-authored Python script under code/")
        if source.stat().st_size > MAX_WRITE_BYTES:
            raise ToolError("Single solver exceeds the 512 KiB review limit")
        return key, source, digest(source)

    def _code_bundle(self):
        files = []
        root = paper.confined(self.workspace, "code", existing=False)
        if not root.is_dir():
            raise ToolError("A model-authored code directory is required")
        for current, directories, names in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name != "__pycache__"]
            for name in directories:
                target = Path(current) / name
                if paper._is_link(target) or paper.private_path(target.relative_to(self.workspace).parts):
                    raise ToolError("Python bundle cannot include private or linked directories")
            for name in names:
                if Path(name).suffix.lower() != ".py":
                    continue
                key = (Path(current) / name).relative_to(self.workspace).as_posix()
                target = paper.confined(self.workspace, key)
                files.append({"path": key, "sha256": digest(target)})
        files.sort(key=lambda item: item["path"])
        canonical = json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return files, hashlib.sha256(canonical).hexdigest()

    def request_solver_execution(self, path):
        key, _, source_hash = self._solver(path)
        code_files, code_tree_hash = self._code_bundle()
        record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "path": key, "sha256": source_hash, "status": "pending_review",
                  "code_tree_hash": code_tree_hash, "code_files": code_files,
                  "execution_started": False}
        target = paper.confined(self.workspace, f"{RUNTIME_ROOT}/workflow-requests.jsonl", existing=False)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        return {**record, "requires_host_review": True,
                "scope": "Request only. Host must independently review and approve the exact entry and entire Python bundle"}

    def _approved(self, key, source_hash, code_tree_hash):
        if not self.approvals.exists():
            return False
        try:
            approval = paper.confined(self.approvals.parent, self.approvals.name,
                                      private=False)
            if approval.stat().st_size > 1024 * 1024:
                raise ToolError("Host approval registry exceeds its bounded size")
            document = json.loads(approval.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ToolError("Host approval registry is unavailable or invalid; ask the host to review it") from exc
        if (not isinstance(document, dict) or set(document) != {"schema_version", "approvals"}
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or not isinstance(document["approvals"], list)):
            raise ToolError("Host approval registry requires schema_version 1 and approvals array")
        seen = set()
        matched = False
        for item in document["approvals"]:
            if (not isinstance(item, dict) or set(item) != {"path", "sha256", "code_tree_hash", "approved"}
                    or not isinstance(item["path"], str) or not isinstance(item["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    or not isinstance(item["code_tree_hash"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["code_tree_hash"])
                    or type(item["approved"]) is not bool):
                raise ToolError("Host approval entry requires path, SHA-256, code_tree_hash and boolean approved")
            normalized = "/".join(paper.relative_parts(item["path"]))
            identity = (normalized, item["sha256"], item["code_tree_hash"])
            if identity in seen:
                raise ToolError("Host approval registry has an ambiguous duplicate entry")
            seen.add(identity)
            if (normalized == key and item["sha256"] == source_hash
                    and item["code_tree_hash"] == code_tree_hash and item["approved"]):
                matched = True
        return matched

    def _protected_snapshot(self):
        record = {}
        for key in sorted(self.protected_paths - {"project-tool-events.jsonl"}):
            target = paper.confined(self.workspace, key, existing=False)
            if target.exists():
                record[key] = digest(target)
        return record

    def _output_inventory(self, byte_budget):
        """Collect all output files, refusing unsupported paths and excess budgets."""
        files, total = [], 0
        for prefix in ('results', 'figures', 'reports'):
            root = paper.confined(self.workspace, prefix, existing=False)
            if not root.exists():
                continue
            if not root.is_dir():
                raise ToolError('Output root must be a real directory: ' + prefix)
            for current, directories, names in os.walk(root, followlinks=False):
                for name in directories:
                    relative = (Path(current) / name).relative_to(self.workspace).as_posix()
                    paper.confined(self.workspace, relative, existing=False)
                for name in names:
                    relative = (Path(current) / name).relative_to(self.workspace).as_posix()
                    target = paper.confined(self.workspace, relative)
                    info = target.stat()
                    if not stat.S_ISREG(info.st_mode):
                        raise ToolError('Output snapshots require ordinary files: ' + relative)
                    if info.st_size > MAX_OUTPUT_FILE_BYTES:
                        raise ToolError('Output exceeds the per-file snapshot budget: ' + relative)
                    total += info.st_size
                    if total > byte_budget:
                        raise ToolError('Output snapshot exceeds the remaining before-plus-after round byte budget')
                    if len(files) >= MAX_OUTPUT_FILES_PER_STAGE:
                        raise ToolError('Output inventory exceeds the per-stage file count budget')
                    files.append({'path': relative, 'bytes': info.st_size, 'sha256': digest(target)})
        return sorted(files, key=lambda item: item['path']), total

    def _store_output_snapshot(self, item):
        """Retain actual bytes once per hash, never replacing a corrupted old blob."""
        relative = f'{RUNTIME_ROOT}/output-history/{item["sha256"]}.bin'
        target = paper.confined(self.workspace, relative, existing=False)
        target.parent.mkdir(exist_ok=True)
        paper.confined(self.workspace, relative, existing=False)
        if target.exists():
            if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
                raise ToolError('Output history snapshot changed; old versions cannot be accepted: ' + relative)
            return relative
        source = paper.confined(self.workspace, item['path'])
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
        copied, source_hash = 0, hashlib.sha256()
        try:
            with source.open('rb') as original, temporary.open('xb') as snapshot:
                for chunk in iter(lambda: original.read(1024 * 1024), b''):
                    copied += len(chunk)
                    if copied > item['bytes'] or copied > MAX_OUTPUT_FILE_BYTES:
                        raise ToolError('Output changed or exceeded its budget while snapshotting: ' + item['path'])
                    source_hash.update(chunk)
                    snapshot.write(chunk)
            if (copied != item['bytes'] or source_hash.hexdigest() != item['sha256']
                    or source.stat().st_size != item['bytes'] or digest(source) != item['sha256']):
                raise ToolError('Output changed while snapshotting: ' + item['path'])
            # Existing blobs are verified and reused. A concurrently appearing
            # blob must likewise match instead of being silently overwritten.
            if target.exists():
                if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
                    raise ToolError('Output history changed during snapshot storage')
            else:
                temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
            raise ToolError('Stored output snapshot failed its SHA-256 check')
        return relative

    def _snapshot_outputs(self, run_dir, stage, byte_budget):
        files, total = self._output_inventory(byte_budget)
        receipts = [{**item, 'snapshot_path': self._store_output_snapshot(item)} for item in files]
        self._verify_output_snapshots(receipts)
        manifest = {'schema_version': 1, 'stage': stage, 'complete': True,
                    'bytes': total, 'files': receipts, 'sha256_verified': True}
        manifest_path = paper.confined(self.workspace,
                                      f'{RUNTIME_ROOT}/{run_dir.name}/outputs-{stage}.json', existing=False)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return manifest

    def _verify_output_snapshots(self, receipts):
        checked = set()
        for item in receipts:
            identity = (item['snapshot_path'], item['sha256'], item['bytes'])
            if identity in checked:
                continue
            target = paper.confined(self.workspace, item['snapshot_path'])
            if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
                raise ToolError('Retained output snapshot failed its SHA-256 check: ' + item['snapshot_path'])
            checked.add(identity)

    @staticmethod
    def _output_changes(before, after):
        old = {item['path']: item for item in before}
        new = {item['path']: item for item in after}
        changes = []
        for path in sorted(old.keys() | new.keys()):
            if path not in old:
                classification = 'created'
            elif path not in new:
                classification = 'deleted'
            elif old[path]['sha256'] != new[path]['sha256']:
                classification = 'modified'
            else:
                classification = 'unchanged'
            changes.append({'path': path, 'classification': classification,
                            'changed_this_run': classification != 'unchanged',
                            'before': old.get(path), 'after': new.get(path)})
        return changes

    def run_approved_solver(self, path):
        key, source, source_hash = self._solver(path)
        code_files, code_tree_hash = self._code_bundle()
        if not self._approved(key, source_hash, code_tree_hash):
            return {"path": key, "sha256": source_hash, "status": "pending_review",
                    "code_tree_hash": code_tree_hash, "code_files": code_files,
                    "execution_started": False, "requires_host_review": True,
                    "scope": "No execution: exact current source hash has no host approval"}
        if self._input_snapshot() != self.frozen_inputs:
            raise ToolError("Inputs changed after startup; solver execution refused")
        run_id = uuid.uuid4().hex
        run_dir = self.runtime / run_id
        run_dir.mkdir()
        for item in code_files:
            original = paper.confined(self.workspace, item["path"])
            source_bytes = original.read_bytes()
            if hashlib.sha256(source_bytes).hexdigest() != item["sha256"]:
                raise ToolError("Python bundle changed during approval check; request review again")
            copied = run_dir / item["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(source_bytes)
        snapshot = run_dir / key
        budget = {'per_file_bytes': MAX_OUTPUT_FILE_BYTES,
                  'before_plus_after_bytes': MAX_OUTPUT_ROUND_BYTES,
                  'files_per_stage': MAX_OUTPUT_FILES_PER_STAGE,
                  'accounting': 'sum of all before and after file sizes, including unchanged/reused files'}
        try:
            before_outputs = self._snapshot_outputs(run_dir, 'before', MAX_OUTPUT_ROUND_BYTES)
        except (ToolError, OSError) as exc:
            result = {'path': key, 'source_sha256': source_hash,
                      'code_tree_hash': code_tree_hash, 'code_files': code_files,
                      'status': 'output_history_failed', 'passed': False, 'execution_started': False,
                      'output_history_complete': False, 'output_history_errors': [self.sanitize(str(exc))],
                      'output_snapshot_budget': budget, 'outputs': [], 'output_changes': None,
                      'run_record': f'{RUNTIME_ROOT}/{run_id}/execution.json',
                      'scientific_correctness_verified': False, 'os_sandbox': False,
                      'scope': 'Execution refused because existing output bytes could not be completely retained within the declared budget'}
            (run_dir / 'execution.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return result
        protected = self._protected_snapshot()
        env = dict(self.env)
        env["PATH"] = str(self.python.parent) + os.pathsep + env.get("PATH", "")
        env["NE_SOURCE_INPUTS"] = str(self.inputs)
        env["PYTHONUTF8"] = "1"
        env["MPLBACKEND"] = "Agg"
        if self.font_dir is not None:
            env["MATHMODEL_CJK_FONT_DIR"] = str(self.font_dir)
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        status, exit_code, stdout, stderr = "executed", None, "", ""
        try:
            process = subprocess.run([str(self.python), "-I", "-B", "-X", "utf8", "-c", SOLVER_LAUNCHER,
                                      str(run_dir / "code"), str(snapshot.parent), str(snapshot)],
                                     cwd=self.workspace, env=env, shell=False, capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=SOLVER_TIMEOUT,
                                     check=False, **kwargs)
            exit_code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as exc:
            status = "timed_out"
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes): stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes): stderr = stderr.decode("utf-8", errors="replace")
        except OSError as exc:
            status, stderr = "execution_failed", str(exc)
        stdout, stderr = self.sanitize(stdout), self.sanitize(stderr)
        (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        try:
            inputs_preserved = self._input_snapshot() == self.frozen_inputs
        except (ToolError, OSError):
            inputs_preserved = False
        try:
            protected_preserved = self._protected_snapshot() == protected
        except (ToolError, OSError):
            protected_preserved = False
        try:
            code_bundle_preserved = self._code_bundle()[1] == code_tree_hash
        except (ToolError, OSError):
            code_bundle_preserved = False
        outputs, output_errors, after_outputs, output_changes = [], [], None, None
        try:
            after_outputs = self._snapshot_outputs(run_dir, 'after',
                                                   MAX_OUTPUT_ROUND_BYTES - before_outputs['bytes'])
            # A reviewed solver still has normal OS privileges. Detect mutation
            # of retained before snapshots rather than claiming OS immutability.
            self._verify_output_snapshots(before_outputs['files'] + after_outputs['files'])
            outputs = [{key: item[key] for key in ('path', 'bytes', 'sha256')}
                       for item in after_outputs['files']]
            output_changes = self._output_changes(before_outputs['files'], after_outputs['files'])
        except (ToolError, OSError) as exc:
            output_errors.append(self.sanitize(str(exc)))
            failure_manifest = paper.confined(self.workspace,
                                             f'{RUNTIME_ROOT}/{run_id}/output-history-error.json', existing=False)
            failure_manifest.write_text(json.dumps({'complete': False, 'errors': output_errors},
                                                    ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result = {"path": key, "source_sha256": source_hash, "status": status,
                  "code_tree_hash": code_tree_hash, "code_files": code_files,
                  "execution_started": True, "exit_code": exit_code,
                  "passed": status == "executed" and exit_code == 0 and inputs_preserved and protected_preserved and code_bundle_preserved and not output_errors,
                  "inputs_preserved": inputs_preserved, "protected_outputs_preserved": protected_preserved,
                  "code_bundle_preserved": code_bundle_preserved,
                  "stdout_tail": stdout[-4000:], "stderr_tail": stderr[-4000:],
                  "outputs": sorted(outputs, key=lambda item: item["path"]),
                  "output_inventory_errors": output_errors,
                  "output_history_complete": not output_errors,
                  "output_history_errors": output_errors,
                  "output_snapshot_budget": budget,
                  "output_history": {'before': before_outputs, 'after': after_outputs},
                  "output_changes": output_changes,
                  "run_record": f"{RUNTIME_ROOT}/{run_id}/execution.json",
                  "scientific_correctness_verified": False, "os_sandbox": False,
                  "scope": "One host-approved Python bundle snapshot, retained before/after output bytes with SHA-256 checks, filesystem change inventory, clean subprocess environment and exit status; unchanged outputs are not newly generated evidence; not scientific verification or an OS sandbox"}
        (run_dir / "execution.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    def event(self, name, result, is_error):
        if name not in {item[0] for item in NEW_TOOLS}:
            return super().event(name, result, is_error)
        # Store actual ranges/source hashes and run outcomes, never source text,
        # input values, stdout, approval contents or host approval paths.
        keys = ("path", "sha256", "before_sha256", "returned_content_sha256",
                "returned_range", "total_lines", "truncated", "next_start_line",
                "status", "execution_started", "source_sha256", "code_tree_hash",
                "code_files", "passed", "exit_code", "inputs_preserved",
                "protected_outputs_preserved", "code_bundle_preserved", "outputs", "run_record",
                "output_history_complete", "output_history_errors", "output_snapshot_budget", "output_changes")
        summary = {key: result[key] for key in keys if key in result}
        if "error" in result:
            summary["error"] = self.sanitize(str(result["error"]))[:500]
        if name == "list_inputs":
            summary["returned_paths"] = [item["path"] for item in result.get("inputs", [])]
            summary["total_items"] = result.get("total_items")
        summary["is_error"] = is_error
        record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "tool": name,
                  "result_summary": summary}
        target = paper.confined(self.workspace, "project-tool-events.jsonl", existing=False)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def call_tool(self, name, arguments):
        if name in {item[0] for item in paper.TOOL_DEFINITIONS}:
            return super().call_tool(name, arguments)
        known = {item[0]: item[2] for item in NEW_TOOLS}
        is_error = False
        try:
            if name not in known:
                raise ToolError("Unknown workflow tool")
            schema = known[name]
            if (not isinstance(arguments, dict) or not set(schema["required"]) <= set(arguments)
                    or set(arguments) - set(schema["properties"])):
                raise ToolError("Arguments must match the advertised workflow tool schema")
            for key, value in arguments.items():
                spec = schema["properties"][key]
                if spec["type"] == "string" and not isinstance(value, str):
                    raise ToolError(key + " must be a string")
                if spec["type"] == "integer" and (type(value) is not int or value < spec.get("minimum", value)
                                                   or value > spec.get("maximum", value)):
                    raise ToolError("Invalid integer field " + key)
            result = getattr(self, name)(**arguments)
            is_error = result.get("passed") is False
        except (ToolError, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            result, is_error = {"error": self.sanitize(str(exc)), "passed": False}, True
        try:
            self.event(name if name in known else "unknown", result, is_error)
        except (ToolError, OSError) as exc:
            result, is_error = {"error": "Workflow audit failed: " + self.sanitize(str(exc)), "passed": False}, True
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result, "isError": is_error}

    def dispatch(self, request):
        # Parent handles validation, notifications and errors. Intercept only the
        # two responses whose interface metadata differ from rendering-only MCP.
        response = super().dispatch(request)
        if response is not None and isinstance(request, dict) and "result" in response:
            if request.get("method") == "initialize":
                response["result"]["serverInfo"] = {"name": "mathmodel-workflow-project", "version": "1.0.0"}
                response["result"]["instructions"] = (
                    "Read the current stage project rules and complete source inventory. This optional research interface lets you write your own code and paper artifacts. "
                    "Request host review before running a Python entry and its complete code bundle; no approval means no execution, and any changed code needs new approval. "
                    "NE_SOURCE_INPUTS is supplied to the approved child only. Use workspace cwd for results; do not write original inputs or accepted PDFs. "
                    "Execution uses an immutable snapshot of all approved code/**/*.py (including local Python modules), fixed Python and no model shell/arguments. "
                    "A normal exit does not validate the model or science. This is not an OS sandbox. Inherit the actual chosen template and check final compiled PDF.")
            elif request.get("method") == "tools/list":
                response["result"]["tools"] = [
                    {"name": name, "description": description, "inputSchema": schema,
                     "annotations": {"readOnlyHint": readonly, "destructiveHint": False,
                                     "idempotentHint": readonly, "openWorldHint": False}}
                    for name, description, schema, readonly in TOOL_DEFINITIONS]
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--python", dest="python_executable", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--drawio", type=Path)
    args = parser.parse_args()
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        server = WorkflowServer(args.workspace, args.inputs, args.python_executable,
                                args.compiler, args.approvals, args.font_dir, args.drawio)
    except (ToolError, ValueError, OSError) as exc:
        print("Workflow server configuration error: " + str(exc), file=sys.stderr)
        return 2
    for line in sys.stdin:
        if not line.strip():
            continue
        request = None
        try:
            if len(line.encode("utf-8")) > paper.MAX_RPC_BYTES:
                raise ValueError("Oversized JSON-RPC request")
            request = json.loads(line)
            response = server.dispatch(request)
        except (ValueError, json.JSONDecodeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON or oversized request"}}
        except Exception as exc:
            print("Workflow request failed: " + server.sanitize(str(exc)), file=sys.stderr)
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32603, "message": "Internal workflow tool error"}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
