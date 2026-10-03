"""Read current paper-template configuration and locally available template variants."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


SKILL = Path(__file__).resolve().parents[1]
DIAGRAM_LABELS = {
    "roadmap-5band": "五带技术路线：问题—数据—方法—结果—评价",
    "framework-3col": "三栏研究框架：阶段—研究内容—方法",
    "stageflow-3col": "三栏阶段流程：阶段推进与分支",
    "taskflow-land": "横版任务流水线：多任务步骤与方法",
}
DATA_ADAPTER_TEMPLATES = {"correlation-pairgrid", "prediction-marginal-grid", "rf-tpe-surface", "paired-raincloud"}


def inspect(project_root: Path, skill_root: Path = SKILL) -> dict:
    project_root = project_root.resolve(strict=True)
    if not project_root.is_dir():
        raise ValueError("Project root must be a directory")
    config_file = project_root / ".mathmodel/paper/config.json"
    selected = None
    if config_file.is_file():
        config = json.loads(config_file.read_text(encoding="utf-8-sig"))
        template = config.get("template", {})
        if not isinstance(template, dict):
            raise ValueError("template configuration must be an object")
        custom = template.get("sourcePath")
        custom_file = (project_root / custom).resolve() if isinstance(custom, str) and custom else None
        selected = {
            "id": template.get("id"),
            "source": template.get("source"),
            "entry_file": template.get("entryFile"),
            "custom_source_present": custom_file is not None,
            "custom_source_exists": custom_file.exists() if custom_file else None,
        }
        entry_file = selected["entry_file"]
        selected["engine"] = ("LaTeX" if isinstance(entry_file, str) and entry_file.endswith(".tex")
                              else "Typst" if isinstance(entry_file, str) and entry_file.endswith(".typ")
                              else None)
        # Deliberately do not expose contestFields or teamProfile.
    template_root = skill_root / "vendor/MathModelAgent/skills/5writing/templates"
    available = []
    if template_root.is_dir():
        for language in sorted(path for path in template_root.iterdir() if path.is_dir()):
            for candidate in sorted(path for path in language.iterdir() if path.is_dir()):
                files = [name for name in ("main.tex", "main.typ") if (candidate / name).is_file()]
                for entry in files:
                    available.append({
                        "language": language.name,
                        "id": candidate.name,
                        "engine": "LaTeX" if entry.endswith(".tex") else "Typst",
                        "entry": (candidate / entry).relative_to(skill_root).as_posix(),
                        "template_source": "vendor",
                    })
    # Project adaptations take precedence for the same language/id/engine,
    # without changing fixed vendor files or any user configuration.
    choices = {(item["language"], item["id"], item["engine"]): item for item in available}
    adaptation_root = skill_root / "assets/templates"
    if adaptation_root.is_dir():
        for language in sorted(path for path in adaptation_root.iterdir() if path.is_dir()):
            for candidate in sorted(path for path in language.iterdir() if path.is_dir()):
                for entry, engine in (("main.tex", "LaTeX"), ("main.typ", "Typst")):
                    if (candidate/entry).is_file():
                        item = {"language": language.name, "id": candidate.name, "engine": engine,
                                "entry": (candidate/entry).relative_to(skill_root).as_posix(),
                                "template_source": "project-adaptation"}
                        profile_file = candidate / "profile.json"
                        if profile_file.is_file():
                            profile = json.loads(profile_file.read_text(encoding="utf-8-sig"))
                            if not isinstance(profile, dict):
                                raise ValueError("Template profile must be an object")
                            for key in ("contest_family", "label", "contest_year", "format_rules_year", "rules_status", "reference"):
                                if key in profile:
                                    item[key] = profile[key]
                        choices[(language.name, candidate.name, engine)] = item
    available = [choices[key] for key in sorted(choices)]
    if selected and isinstance(selected["id"], str):
        base = selected["id"].removesuffix("-latex")
        selected["matching_variants"] = [
            item["id"] for item in available
            if item["id"] in {base, base + "-latex"}
            and (selected["engine"] is None or item["engine"] == selected["engine"])
        ]
    diagram_root = skill_root / "vendor/sci-box/skills/scibox-diagram"
    diagrams = []
    for name, label in DIAGRAM_LABELS.items():
        example = diagram_root / "assets" / name / "example.json"
        preview = diagram_root / "assets" / name / "preview.png"
        if example.is_file():
            diagrams.append({"id": name, "label": label,
                             "example": example.relative_to(skill_root).as_posix(),
                             "preview": preview.relative_to(skill_root).as_posix() if preview.is_file() else None})
    catalog = skill_root / "vendor/MathModelAgent/skills/mathmodel-figure-templates/references/figure-catalog.md"
    figure_root = catalog.parents[1]
    data_figures = []
    if catalog.is_file():
        for line in catalog.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|", line)
            if not match:
                continue
            name, script_name, label = match.groups()
            script = figure_root / "scripts/templates" / script_name
            if not script.is_file():
                continue
            preview = figure_root / "assets/previews" / (name.replace("-", "_") + "_replica.png")
            data_figures.append({"id": name, "label": label.strip(),
                                 "script": script.relative_to(skill_root).as_posix(),
                                 "preview": preview.relative_to(skill_root).as_posix() if preview.is_file() else None,
                                 "default_data": "simulated; replace and verify before paper use",
                                 "data_adapter": "scripts/render_scientific_data.py" if name in DATA_ADAPTER_TEMPLATES and (skill_root / "scripts/render_scientific_data.py").is_file() else None,
                                 "adapter_note": "CSV role contract required; metrics are computed and sparse surfaces rejected" if name in DATA_ADAPTER_TEMPLATES else "Original template is style-only until data and statistics are adapted"})
    # The project ROC adapter deliberately has its own identity. It must not
    # imply that the upstream cv-roc-ci confidence bands are implemented.
    roc_manifest=skill_root/'examples/scientific-figures/binary-roc.json'
    if roc_manifest.is_file() and (skill_root/'scripts/render_scientific_data.py').is_file():
        roc_preview=skill_root/'docs/figures/scientific/binary-roc/figure.png'
        data_figures.append({'id':'binary-roc-comparison','label':'二元ROC比较：同一样本标签与真实得分，无折间CI',
                             'script':'scripts/render_scientific_data.py','preview':roc_preview.relative_to(skill_root).as_posix() if roc_preview.is_file() else None,
                             'template_source':'project-adaptation','default_data':'none; explicit CSV role contract required',
                             'example':roc_manifest.relative_to(skill_root).as_posix(),'data_adapter':'scripts/render_scientific_data.py',
                             'adapter_note':'Empirical binary ROC/AUC; no training, fold analysis or confidence intervals'})
    flow_root=skill_root/'examples/flowcharts'
    if (skill_root/'scripts/render_flowchart.py').is_file() and flow_root.is_dir():
        for manifest in sorted(flow_root.glob('*.json')):
            spec=json.loads(manifest.read_text(encoding='utf-8'))
            native_preview=skill_root/'docs/figures/flowcharts'/manifest.stem/'figure.png'
            diagrams.append({'id':'project-flowchart/'+manifest.stem,'label':spec['title'],
                             'example':manifest.relative_to(skill_root).as_posix(),'preview':native_preview.relative_to(skill_root).as_posix() if native_preview.is_file() else None,
                             'template_source':'project-adaptation','script':'scripts/render_flowchart.py',
                             'layout':'authored coordinates, labeled conditions and explicit feedback lanes; no automatic layout claim'})
    return {"project_root": str(project_root), "configured": selected,
            "available": available, "diagram_templates": diagrams,
            "data_figure_templates": data_figures,
            "vendor_templates_present": template_root.is_dir(),
            "note": "Inventory only; no files copied and no template decision made"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, default=SKILL)
    parser.add_argument("--category", choices=("all", "paper", "diagram", "data-figure"), default="all")
    parser.add_argument("--language", choices=("zh", "en"), help="Filter paper template variants")
    parser.add_argument("--configured-family", action="store_true",
                        help="Show only paper variants matching the configured contest id")
    parser.add_argument("--family", help="Filter an explicitly selected family, e.g. mathorcup-bigdata; does not change config")
    args = parser.parse_args()
    try:
        result = inspect(args.project_root, args.skill_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.language:
        result["available"] = [item for item in result["available"] if item["language"] == args.language]
    if args.family:
        base = args.family.removesuffix("-latex")
        result["available"] = [item for item in result["available"] if item["id"] in {base, base + "-latex"}]
    elif args.configured_family and result["configured"] and isinstance(result["configured"]["id"], str):
        base = result["configured"]["id"].removesuffix("-latex")
        result["available"] = [item for item in result["available"]
                               if item["id"] in {base, base + "-latex"}]
    if args.category != "all":
        choices = {"paper": result["available"], "diagram": result["diagram_templates"],
                   "data-figure": result["data_figure_templates"]}[args.category]
        result = {"configured": result["configured"], "category": args.category, "choices": choices,
                  "note": result["note"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
