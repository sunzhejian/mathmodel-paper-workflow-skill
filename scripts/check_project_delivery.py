"""Check a project's declared deliverables and per-question files without running code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


MODES = {"revise", "write-from-results", "full-delivery", "review-only", "diagram-only", "layout-only"}


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def local_path(root: Path, value, label: str) -> tuple[str, Path]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected nonempty project-relative path")
    normalized = value.replace("\\", "/")
    if ":" in normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError(f"{label}: path must stay inside project root")
    path = (root / normalized).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{label}: path escapes project root through a symlink")
    return Path(normalized).as_posix(), path


def identifier(value, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise ValueError(f"{label}: use a short identifier containing letters, digits, underscore, dot or hyphen")
    return value


def check(manifest_path: Path, project_root: Path) -> tuple[dict, set[Path]]:
    root = project_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project-root must be a directory")
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Manifest requires schema_version 1")
    mode = manifest.get("mode")
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("Manifest mode must match one of the six workflow directions")
    outputs = manifest.get("deliverables")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Manifest requires a nonempty deliverables array")
    questions = manifest.get("questions", [])
    preserved = manifest.get("preserved_inputs", [])
    if not isinstance(questions, list) or not isinstance(preserved, list):
        raise ValueError("questions and preserved_inputs must be arrays")
    if mode == "full-delivery" and not questions:
        raise ValueError("full-delivery requires the actual question list")

    protected = {manifest_path}
    failures: list[str] = []
    output_records, question_records, preserved_records = [], [], []
    seen_ids, seen_paths = set(), set()
    required_count = 0

    def inspect(value, label, required=True):
        relative, path = local_path(root, value, label)
        protected.add(path)
        record = {"path": relative, "present": path.is_file()}
        if not path.is_file():
            if required:
                failures.append(f"{label}: missing file")
            return record
        record.update(size=path.stat().st_size, sha256=file_hash(path))
        if record["size"] == 0:
            failures.append(f"{label}: empty file")
        return record

    for index, item in enumerate(outputs, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Deliverable {index}: expected object")
        name = identifier(item.get("id"), f"Deliverable {index} id")
        if name.casefold() in seen_ids:
            raise ValueError(f"Deliverable {index}: duplicate id")
        seen_ids.add(name.casefold())
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(f"Deliverable {index}: required must be true or false")
        required_count += int(required)
        record = inspect(item.get("path"), f"Deliverable {name}", required)
        key = record["path"].casefold()
        if key in seen_paths:
            raise ValueError(f"Deliverable {index}: duplicate or case-colliding path")
        seen_paths.add(key)
        output_records.append({"id": name, "required": required, **record})
    if not required_count:
        raise ValueError("At least one deliverable must be required")

    seen_questions = set()
    for index, item in enumerate(questions, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {index}: expected object")
        name = identifier(item.get("id"), f"Question {index} id")
        if name.casefold() in seen_questions:
            raise ValueError(f"Question {index}: duplicate id")
        seen_questions.add(name.casefold())
        command = item.get("run_command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"Question {name}: record the actual run_command")
        results = item.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError(f"Question {name}: requires at least one result path")
        solver = inspect(item.get("solver"), f"Question {name} solver")
        records = [inspect(value, f"Question {name} result {j}") for j, value in enumerate(results, 1)]
        question_records.append({"id": name, "solver": solver, "results": records,
                                 "run_command_recorded": True, "run_command_executed_by_checker": False})

    for index, item in enumerate(preserved, 1):
        if not isinstance(item, dict) or not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]):
            raise ValueError(f"Preserved input {index}: requires a real SHA-256 baseline")
        record = inspect(item.get("path"), f"Preserved input {index}")
        matches = record.get("sha256") == item["sha256"].lower()
        if record["present"] and not matches:
            failures.append(f"Preserved input {index}: content changed from baseline")
        preserved_records.append({**record, "matches_baseline": matches})

    return {"schema_version": 1, "mode": mode, "manifest_sha256": file_hash(manifest_path),
            "inventory_complete": not failures, "required_deliverables": required_count,
            "deliverables": output_records, "questions": question_records,
            "preserved_inputs": preserved_records, "failures": failures,
            "scope": "Declared nonempty files and preserved-input hashes only; commands are not executed; model, format, citations and visual checks remain separate"}, protected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path, help="New project-relative JSON report")
    args = parser.parse_args(argv)
    try:
        result, protected = check(args.manifest, args.project_root)
        root = args.project_root.resolve(strict=True)
        _, report = local_path(root, str(args.report), "report")
        if report in protected or report.exists():
            raise ValueError("Use a new report path distinct from all declared files")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({"inventory_complete": result["inventory_complete"],
                          "required_deliverables": result["required_deliverables"],
                          "questions_checked": len(result["questions"]),
                          "failures": result["failures"]}, ensure_ascii=False))
        return 0 if result["inventory_complete"] else 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
