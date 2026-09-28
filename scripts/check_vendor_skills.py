"""Verify pinned upstream skill submodules and their selected local entrypoints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER_NAME = re.compile(r"(?m)^name:\s*['\"]?([^\r\n'\"]+)['\"]?\s*$")


def inspect(root: Path) -> dict:
    lock = json.loads((root / "examples/upstream-lock.json").read_text(encoding="utf-8"))
    registry = json.loads((root / "vendor/skill-integrations.json").read_text(encoding="utf-8"))
    sources = {item["name"]: item for item in lock["sources"]}
    findings: list[str] = []
    checked: list[dict] = []
    heads: dict[str, str | None] = {}
    for name, source in sources.items():
        directory = root / "vendor" / name
        if not directory.is_dir():
            findings.append(f"{name}: submodule is absent; run git submodule update --init --recursive")
            heads[name] = None
            continue
        proc = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8")
        head = proc.stdout.strip() if proc.returncode == 0 else None
        heads[name] = head
        if head != source["commit"]:
            findings.append(f"{name}: expected {source['commit']}, found {head or 'no Git checkout'}")
        configured = subprocess.run(
            ["git", "config", "-f", str(root / ".gitmodules"),
             f"submodule.vendor/{name}.url"],
            capture_output=True, text=True, encoding="utf-8")
        url = configured.stdout.strip() if configured.returncode == 0 else None
        if url != source["url"] + ".git":
            findings.append(f"{name}: expected .gitmodules URL {source['url']}.git, found {url!r}")
    seen: set[str] = set()
    for skill in registry["skills"]:
        name = skill["name"]
        source = skill["source"]
        if name in seen:
            findings.append(f"{name}: duplicate selected skill name")
        seen.add(name)
        if source not in sources:
            findings.append(f"{name}: unknown source {source}")
            continue
        relative = Path(skill["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".md":
            findings.append(f"{name}: invalid entrypoint path {relative}")
            continue
        entrypoint = root / "vendor" / source / relative
        if not entrypoint.is_file():
            findings.append(f"{name}: missing {entrypoint.relative_to(root)}")
            continue
        content = entrypoint.read_text(encoding="utf-8-sig")
        match = FRONTMATTER_NAME.search(content.split("---", 2)[1] if content.startswith("---") else "")
        declared = match.group(1).strip() if match else None
        if declared != name:
            findings.append(f"{name}: frontmatter declares {declared!r}")
        checked.append({"name": name, "source": source, "path": entrypoint.relative_to(root).as_posix(),
                        "stage": skill["stage"], "usage": skill["usage"]})
    return {"ok": not findings, "source_commits": heads, "checked_skills": checked,
            "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Skill repository root")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args()
    try:
        result = inspect(args.root.resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Vendor manifest error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Checked {len(result['checked_skills'])} skill entrypoints across "
              f"{len(result['source_commits'])} pinned projects")
        for finding in result["findings"]:
            print(f"FAIL {finding}")
        if result["ok"]:
            print("PASS all selected skill files and source commits match the manifest")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
