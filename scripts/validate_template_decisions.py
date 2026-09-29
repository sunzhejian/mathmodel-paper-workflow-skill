"""Check recorded paper, diagram, and data-figure choices against local templates."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("template_inventory", ROOT / "scripts/template_inventory.py")
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


def validate(project_root: Path, decisions_file: Path, skill_root: Path = ROOT) -> dict:
    project_root = project_root.resolve(strict=True)
    records = json.loads(decisions_file.read_text(encoding="utf-8-sig"))
    if not isinstance(records, dict) or not isinstance(records.get("decisions"), list) or not records["decisions"]:
        raise ValueError("Decision file requires a nonempty decisions array")
    inventory = INVENTORY.inspect(project_root, skill_root)
    paper: dict[str, list[dict]] = {}
    for option in inventory["available"]:
        paper.setdefault(option["id"], []).append(option)
    diagrams = {item["id"] for item in inventory["diagram_templates"]}
    data_figures = {item["id"] for item in inventory["data_figure_templates"]}
    seen = set()
    findings = []
    checked = []
    for number, item in enumerate(records["decisions"], 1):
        if not isinstance(item, dict):
            findings.append(f"Decision {number}: expected object")
            continue
        kind, target, choice = (item.get(key) for key in ("kind", "target", "choice"))
        basis = item.get("basis")
        if kind not in {"paper", "diagram", "data-figure"} or not isinstance(target, str) or not target.strip():
            findings.append(f"Decision {number}: invalid kind or target")
            continue
        if not isinstance(choice, str) or not choice.strip() or basis not in {"user", "project-config", "inferred"}:
            findings.append(f"Decision {number}: missing choice or basis")
            continue
        key = (kind, target.casefold())
        if key in seen:
            findings.append(f"Decision {number}: duplicate {kind}/{target}")
        seen.add(key)
        if kind == "paper":
            if choice not in paper and choice != "custom":
                findings.append(f"Decision {number}: unavailable paper template {choice}")
            if choice in paper:
                languages = {option["language"] for option in paper[choice]}
                language = item.get("language")
                if len(languages) > 1 and language not in languages:
                    findings.append(f"Decision {number}: ambiguous paper language for {choice}")
                elif language is not None and language not in languages:
                    findings.append(f"Decision {number}: unavailable paper language {language}")
            if basis == "project-config":
                configured = inventory["configured"]
                family = configured["id"].removesuffix("-latex") if configured and isinstance(configured["id"], str) else None
                if family is None or choice not in {family, family + "-latex"}:
                    findings.append(f"Decision {number}: project-config paper choice no longer matches config")
                elif choice in paper and configured["engine"] and all(
                        option["engine"] != configured["engine"] for option in paper[choice]):
                    findings.append(f"Decision {number}: project-config paper engine no longer matches config")
            if choice == "custom" and not _source_exists(project_root, item.get("source_path")):
                findings.append(f"Decision {number}: custom paper source is missing")
        elif kind == "diagram":
            if choice not in diagrams | {"custom", "none"}:
                findings.append(f"Decision {number}: unavailable diagram template {choice}")
        elif choice not in data_figures | {"custom", "none"}:
            findings.append(f"Decision {number}: unavailable data-figure template {choice}")
        elif choice not in {"none"}:
            if not _source_exists(project_root, item.get("source_data")):
                findings.append(f"Decision {number}: data figure needs an existing source_data file")
            if choice in data_figures and item.get("simulated_data_replaced") is not True:
                findings.append(f"Decision {number}: bundled data-figure example must be replaced")
        checked.append({"kind": kind, "target": target, "choice": choice, "basis": basis})
    return {"passed": not findings, "checked": checked, "findings": findings,
            "note": "Checks file availability and consistency, not whether the user actually confirmed a choice"}


def _source_exists(project_root: Path, value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = validate(args.project_root, args.decisions, args.skill_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
