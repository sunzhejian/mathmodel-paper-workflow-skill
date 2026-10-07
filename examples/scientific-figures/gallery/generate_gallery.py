"""Generate anonymous, deterministic scientific gallery samples and thumbnails.

These inputs demonstrate figure contracts. They are not contest observations,
trained models, solver results or scientific conclusions. No data are fetched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
SEED = 20261007
IDS = (
    "grouped-line", "uncertainty-band", "grouped-scatter", "grouped-box",
    "grouped-violin", "distribution-histogram", "ecdf-distribution", "grouped-bar",
    "stacked-bar", "matrix-heatmap", "residual-diagnostics", "binary-pr-comparison",
    "confusion-matrix", "optimization-convergence", "pareto-front",
)
TITLES = {
    "grouped-line": "分组曲线", "uncertainty-band": "给定范围带",
    "grouped-scatter": "分组散点", "grouped-box": "分组箱线",
    "grouped-violin": "分组小提琴", "distribution-histogram": "分布直方图",
    "ecdf-distribution": "经验累积分布", "grouped-bar": "分组柱状",
    "stacked-bar": "堆叠柱状", "matrix-heatmap": "矩阵热图",
    "residual-diagnostics": "残差诊断", "binary-pr-comparison": "精确率–召回率比较",
    "confusion-matrix": "混淆矩阵", "optimization-convergence": "目标轨迹",
    "pareto-front": "非支配解前沿",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def datasets():
    """Return each source table; draw statistics must be computed by the adapter."""
    tables = {}
    tables["grouped-line"] = [
        {"group": f"方案{letter}", "x": hour, "y": round(8 + offset + 1.2 * hour + .7 * np.sin(hour / 2 + offset), 6)}
        for letter, offset in (("A", 0), ("B", 2), ("C", 4)) for hour in range(13)
    ]
    tables["uncertainty-band"] = []
    for letter, offset in (("A", 0), ("B", 2.0)):
        for hour in range(13):
            center = 6 + offset + 1.1 * hour + .5 * np.sin(hour / 2)
            half_width = .8 + .04 * hour
            tables["uncertainty-band"].append({"group": f"方案{letter}", "x": hour,
                "estimate": round(center, 6), "lower": round(center - half_width, 6), "upper": round(center + half_width, 6)})
    rng = np.random.default_rng(SEED + 2)
    tables["grouped-scatter"] = [
        {"group": f"组{letter}", "sample_id": f"{letter}{i:03d}", "x": round(x, 6),
         "y": round(6 + k * 4 + .6 * x + rng.normal(0, 2.3), 6)}
        for k, letter in enumerate("ABC") for i, x in enumerate(rng.uniform(1, 20, 36), 1)
    ]
    for index, kind in enumerate(("grouped-box", "grouped-violin", "distribution-histogram", "ecdf-distribution"), 3):
        rng = np.random.default_rng(SEED + index)
        tables[kind] = [
            {"group": f"组{letter}", "sample_id": f"{letter}{i:03d}", "value": round(value, 6)}
            for k, letter in enumerate("ABC") for i, value in enumerate(rng.normal(20 + 5 * k, 2.8 + .5 * k, 45), 1)
        ]
    bar_values = ((12, 9, 7), (15, 11, 6), (13, 14, 8), (17, 12, 9))
    for kind in ("grouped-bar", "stacked-bar"):
        tables[kind] = [{"category": f"条件{i + 1}", "series": f"分量{'ABC'[j]}", "value": value}
                        for i, values in enumerate(bar_values) for j, value in enumerate(values)]
    tables["matrix-heatmap"] = [{"row": f"对象{i + 1}", "column": f"指标{j + 1}",
                                 "value": round(.25 + .1 * i + .07 * j + .09 * np.sin(i + j), 6)}
                                for i in range(5) for j in range(5)]
    rng = np.random.default_rng(SEED + 10)
    tables["residual-diagnostics"] = []
    for i in range(64):
        actual = 10 + i * 1.1 + 3 * np.sin(i / 7)
        split = "训练集" if i < 40 else "验证集"
        for model, scale in (("模型A", 2.6), ("模型B", 4.2)):
            tables["residual-diagnostics"].append({"model": model, "split": split, "sample_id": f"s{i + 1:03d}",
                "actual": round(actual, 6), "predicted": round(actual + rng.normal(0, scale) + .018 * (actual - 45), 6)})
    rng = np.random.default_rng(SEED + 11)
    tables["binary-pr-comparison"] = []
    labels = np.array([1] * 35 + [0] * 55)
    rng.shuffle(labels)
    for model, strength in (("模型A", 1.65), ("模型B", 1.15), ("模型C", .7)):
        scores = 1 / (1 + np.exp(-(strength * (labels * 2 - 1) + rng.normal(0, 1.15, len(labels)))))
        for i, (label, score) in enumerate(zip(labels, scores), 1):
            tables["binary-pr-comparison"].append({"model": model, "sample_id": f"s{i:03d}",
                                                  "label": int(label), "score": round(score, 7)})
    rng = np.random.default_rng(SEED + 12)
    tables["confusion-matrix"] = []
    classes = np.array(["类A", "类B", "类C"])
    actual_classes = np.resize(classes, 75)
    for model, probability in (("模型A", .84), ("模型B", .68)):
        for i, actual in enumerate(actual_classes, 1):
            predicted = actual if rng.uniform() < probability else rng.choice(classes[classes != actual])
            tables["confusion-matrix"].append({"model": model, "sample_id": f"s{i:03d}",
                                             "actual": str(actual), "predicted": str(predicted)})
    tables["optimization-convergence"] = [
        {"group": f"方案{letter}", "iteration": iteration,
         "objective": round(floor + 80 * np.exp(-rate * iteration) + 2 / (iteration + 1), 7)}
        for letter, rate, floor in (("A", .16, 8), ("B", .10, 10), ("C", .075, 12)) for iteration in range(46)
    ]
    rng = np.random.default_rng(SEED + 14)
    tables["pareto-front"] = []
    for group in ("方案A", "方案B"):
        for i in range(36):
            x = rng.uniform(2, 10)
            y = 2.5 / (x - .6) + rng.uniform(0, .9)
            tables["pareto-front"].append({"group": group, "sample_id": f"{group[-1]}{i + 1:03d}",
                                           "x": round(x, 6), "y": round(y, 6)})
    return tables


def contract(kind, metadata):
    spec = {"schema_version": 1, "template_id": kind, "data_kind": "synthetic", "data": f"{kind}.csv",
            "title": TITLES[kind], "source_note": f"合成示例；generate_gallery.py::datasets，固定种子 {SEED} 及逐类偏移；仅说明合同和绘图行为，非实验、训练或赛题结果。",
            "roles": {role: role for role in metadata["roles"]}}
    axes = {
        "grouped-line": {"x": {"label": "时间", "unit": "h"}, "y": {"label": "响应值", "unit": "1"}},
        "uncertainty-band": {"x": {"label": "时间", "unit": "h"}, "estimate": {"label": "给定中心值", "unit": "1"}},
        "grouped-scatter": {"x": {"label": "输入变量", "unit": "1"}, "y": {"label": "响应变量", "unit": "1"}},
        "residual-diagnostics": {"actual": {"label": "参考值", "unit": "1"}, "predicted": {"label": "给定预测值", "unit": "1"}},
        "optimization-convergence": {"iteration": {"label": "迭代序号", "unit": "1"}, "objective": {"label": "给定目标值", "unit": "1"}},
        "pareto-front": {"x": {"label": "目标一", "unit": "1"}, "y": {"label": "目标二", "unit": "1"}},
    }
    if metadata.get("axes"):
        spec["axes"] = axes[kind]
    if metadata.get("unit"):
        spec["unit"] = "1"
    if kind == "uncertainty-band":
        spec["interval_note"] = "范围为合成规则给定的上下界；不是由样本推算的置信区间。"
    if kind == "pareto-front":
        spec.update(x_direction="min", y_direction="min")
    missing = set(metadata.get("required_fields", ())) - set(spec)
    if missing:
        raise ValueError(f"Metadata requires unimplemented sample fields: {kind}: {sorted(missing)}")
    return spec


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def thumbnail(source, target, font, *, kind, labelled=True):
    """Resize the native export, which already labels its synthetic provenance."""
    with Image.open(source) as opened:
        rgb = opened.convert("RGB")
        height = round(rgb.height * 640 / rgb.width)
        image = rgb.resize((640, height), Image.Resampling.LANCZOS)
    if not labelled:
        padded = Image.new("RGB", (640, height + 38), "white")
        padded.paste(image, (0, 38))
        draw = ImageDraw.Draw(padded)
        face = ImageFont.truetype(str(font), 22)
        draw.text((16, 8), "合成示例 · " + kind, font=face, fill="#202A35")
        image = padded
    # Quality is kept at the explicit requested 88. Optimize encoding, not text.
    image.save(target, "JPEG", quality=88, optimize=True, progressive=True, subsampling=0)
    sampling = 0
    if Path(target).stat().st_size > 40 * 1024:
        image.save(target, "JPEG", quality=88, optimize=True, progressive=True, subsampling=2)
        sampling = 2
    return {"width": 640, "height": image.height, "bytes": Path(target).stat().st_size,
            "sha256": sha(target), "encoding": "JPEG", "quality": 88, "subsampling": sampling, "source": str(source)}


def gallery_labels(fig, spec):
    """Localize display strings without changing supplied values/statistics."""
    exact = {"Observations": "观测数", "Residual distribution": "残差分布",
             "Predicted class": "预测类别", "Observed class": "参考类别",
             "Empirical cumulative probability": "经验累计概率", "Recall": "召回率", "Precision": "精确率",
             "Nondominated supplied candidates": "给定候选中的非支配解"}
    def translate(text):
        if text in exact:
            return exact[text]
        if text.startswith("Value ("):
            return text.replace("Value (", "数值 (")
        if text.startswith("Residual ("):
            return text.replace("Residual (", "残差 (")
        if text.startswith("Predicted - observed ("):
            return text.replace("Predicted - observed (", "给定预测值 - 参考值 (")
        if text.startswith("Cohort prevalence ("):
            return text.replace("Cohort prevalence (", "样本正例比例 (")
        return text
    for ax in fig.axes:
        ax.set_xlabel(translate(ax.get_xlabel()))
        ax.set_ylabel(translate(ax.get_ylabel()))
        ax.set_title(translate(ax.get_title()))
        legend = ax.get_legend()
        if legend:
            for label in legend.get_texts():
                label.set_text(translate(label.get_text()))
                label.set_fontsize(8.5)
    for item in fig.texts:
        if spec["template_id"] == "binary-pr-comparison":
            item.set_text("给定分数；并列阈值同时更新；AP按召回率增量加权。")
        elif spec["template_id"] == "pareto-front":
            item.set_text("目标一、目标二均最小化；仅比较给定候选。")
        item.set_fontsize(8.5)


def render_charts(output, font):
    from scientific_chart_extensions import EXTENSIONS, prepare_extension, render_extension
    from render_scientific_data import register_font
    tables = datasets()
    missing = set(IDS) - set(EXTENSIONS)
    if missing:
        raise ValueError(f"Extension module is missing sample families: {sorted(missing)}")
    os.environ["MPLCONFIGDIR"] = str(output / ".mplconfig")
    import matplotlib as mpl
    mpl.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    family, font_record = register_font(font, output, font_manager)
    mpl.rcParams.update({"font.family": family, "font.size": 10, "axes.labelsize": 10,
                         "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.titlesize": 10,
                         "axes.linewidth": .75, "axes.unicode_minus": False,
                         "text.color": "#202A35", "axes.labelcolor": "#202A35",
                         "xtick.color": "#202A35", "ytick.color": "#202A35",
                         "figure.facecolor": "white", "axes.facecolor": "white",
                         "svg.fonttype": "none", "pdf.fonttype": 42})
    records = []
    for kind in IDS:
        spec = contract(kind, EXTENSIONS[kind])
        csv_path, manifest_path = HERE / f"{kind}.csv", HERE / f"{kind}.json"
        write_csv(csv_path, tables[kind])
        save_json(manifest_path, spec)
        with csv_path.open(encoding="utf-8", newline="") as stream:
            source_rows = list(csv.DictReader(stream))
        bundle = prepare_extension(spec, source_rows)
        fig = render_extension(spec, bundle, plt)
        if fig is None:
            fig = plt.gcf()
        gallery_labels(fig, spec)
        fig.suptitle(TITLES[kind] + "（合成示例）", fontsize=14, color="#202A35", y=.99)
        folder = output / kind
        folder.mkdir()
        exports = {}
        for suffix in ("png", "pdf", "svg"):
            destination = folder / f"figure.{suffix}"
            fig.savefig(destination, dpi=300, bbox_inches="tight", pad_inches=.1, facecolor="white")
            exports[suffix] = {"file": str(destination), "sha256": sha(destination), "bytes": destination.stat().st_size}
        plt.close(fig)
        thumb_path = HERE / f"{kind}.jpg"
        thumb = thumbnail(folder / "figure.png", thumb_path, font, kind=TITLES[kind])
        report = {"template_id": kind, "data_kind": "synthetic", "seed": SEED,
                  "generator": str(Path(__file__)), "generator_sha256": sha(__file__),
                  "input": str(csv_path), "input_sha256": sha(csv_path), "contract": str(manifest_path),
                  "contract_sha256": sha(manifest_path), "extension_sha256": sha(ROOT / "scripts/scientific_chart_extensions.py"),
                  "rows": len(source_rows), "statistics": bundle.get("statistics", {}),
                  "source_note": spec["source_note"], "font": font_record,
                  "numpy_version": np.__version__, "matplotlib_version": mpl.__version__,
                  "outputs": exports, "thumbnail": {"file": str(thumb_path), **thumb},
                  "scope": "Anonymous gallery demonstration; no experiment, model training or optimizer execution."}
        save_json(folder / "figure-data.json", report)
        records.append(report)
        print(json.dumps({"template_id": kind, "rows": len(source_rows), "thumbnail_bytes": thumb["bytes"]}, ensure_ascii=False), flush=True)
    return records


def node(ident, label, kind, x, y, width, height, **extra):
    return dict(id=ident, label=label, kind=kind, x=x, y=y, width=width, height=height, **extra)


def edge(ident, source, target, **extra):
    return dict(id=ident, source=source, target=target, relation="process", **extra)


def port(side, position=.5):
    return {"side": side, "position": position}


def points(*items):
    return [{"x": x, "y": y} for x, y in items]


def flow_contracts():
    common = {"schema_version": 1, "data_kind": "schematic", "groups": [],
              "source_note": "合成示例；由 generate_gallery.py::flow_contracts 明确编写的匿名通用机制，须按真实题面和方法替换；不表示算法或试验已经执行。",
              "style": {"font_family": "SimSun", "font_size": 22, "publication_width_mm": 160,
                        "minimum_font_pt": 8.5, "maximum_height_mm": 225, "minimum_dpi": 300}}
    header = lambda title, width: node("synthetic_banner", "合成示例 · " + title, "annotation", 15, 5, width - 30, 42)
    roadmap = dict(common, title="全文研究路线", claim="研究从问题与数据出发，连接数据处理、模型设计、求解验证和结果表达。", canvas={"width": 840, "height": 590})
    roadmap["nodes"] = [header(roadmap["title"], 840),
        node("problem", "问题与资料\n确定目标与约束", "input", 285, 65, 270, 66),
        node("data", "数据处理\n字段、单位与质量", "process", 45, 190, 300, 66),
        node("model", "模型设计\n假设、变量与关系", "process", 495, 190, 300, 66),
        node("solve", "数值求解\n生成可追溯输出", "process", 285, 315, 270, 66),
        node("validate", "验证与敏感性分析", "process", 285, 410, 270, 60),
        node("report", "结果、图表与结论", "output", 265, 520, 310, 60)]
    roadmap["edges"] = [
        edge("problem_data", "problem", "data", source_port=port("south", .25), target_port=port("north"), waypoints=points((352.5, 160), (195, 160))),
        edge("problem_model", "problem", "model", source_port=port("south", .75), target_port=port("north"), waypoints=points((487.5, 160), (645, 160))),
        edge("data_solve", "data", "solve", source_port=port("south"), target_port=port("north", .2), waypoints=points((195, 285), (339, 285))),
        edge("model_solve", "model", "solve", source_port=port("south"), target_port=port("north", .8), waypoints=points((645, 285), (501, 285))),
        edge("solve_validate", "solve", "validate"), edge("validate_report", "validate", "report")]
    pipeline = dict(common, title="数据处理与划分", claim="字段单位校验失败时补齐资料；完成明确变换后划分训练、验证与测试集。", canvas={"width": 900, "height": 630})
    pipeline["nodes"] = [header(pipeline["title"], 900),
        node("input", "原始数据与字典", "input", 300, 65, 280, 60),
        node("check", "数据可用？", "decision", 280, 170, 320, 140, condition_label="字段单位完整？"),
        node("repair", "补齐字段与单位", "process", 655, 208, 230, 66),
        node("transform", "清理与明确变换", "process", 300, 365, 280, 64),
        node("train", "训练集\n仅此集估计参数", "output", 25, 535, 260, 72),
        node("validation", "验证集\n比较候选方法", "output", 310, 535, 260, 72),
        node("test", "测试集\n一次评价表现", "output", 605, 535, 270, 72)]
    pipeline["edges"] = [edge("input_check", "input", "check"),
        edge("complete", "check", "transform", label="是", label_offset={"x": 28, "y": 0}),
        edge("incomplete", "check", "repair", label="否", source_port=port("east"), target_port=port("west"), label_offset={"x": 0, "y": -20}),
        dict(edge("repair_check", "repair", "check", source_port=port("north"), target_port=port("north"), waypoints=points((770, 147), (440, 147))), relation="feedback"),
        edge("to_train", "transform", "train", source_port=port("south", .2), target_port=port("north"), waypoints=points((356, 485), (155, 485))),
        edge("to_validation", "transform", "validation", source_port=port("south"), target_port=port("north")),
        edge("to_test", "transform", "test", source_port=port("south", .8), target_port=port("north"), waypoints=points((524, 485), (740, 485)))]
    model = dict(common, title="模型模块与汇流", claim="输入与参数汇入状态接口，三个抽象模块独立计算并汇总输出。", canvas={"width": 860, "height": 620})
    model["groups"] = [{"id": "modules", "label": "模型模块", "x": 15, "y": 300, "width": 830, "height": 165}]
    model["nodes"] = [header(model["title"], 860),
        node("observations", "输入数据", "input", 50, 80, 250, 65),
        node("parameters", "参数与条件", "input", 560, 80, 250, 65),
        node("interface", "状态与变量接口", "process", 300, 205, 260, 70),
        node("module_a", "模块一\n状态估计", "process", 35, 355, 240, 65, group="modules"),
        node("module_b", "模块二\n约束计算", "process", 310, 355, 240, 65, group="modules"),
        node("module_c", "模块三\n目标评价", "process", 585, 355, 240, 65, group="modules"),
        node("summary", "汇总结果与校验量", "output", 270, 545, 320, 65)]
    model["edges"] = [
        edge("data_interface", "observations", "interface", source_port=port("south"), target_port=port("north", .2), waypoints=points((175, 175), (352, 175))),
        edge("params_interface", "parameters", "interface", source_port=port("south"), target_port=port("north", .8), waypoints=points((685, 175), (508, 175))),
        edge("to_a", "interface", "module_a", source_port=port("west"), target_port=port("north"), waypoints=points((155, 240))),
        edge("to_b", "interface", "module_b", source_port=port("south"), target_port=port("north")),
        edge("to_c", "interface", "module_c", source_port=port("east"), target_port=port("north"), waypoints=points((705, 240))),
        edge("a_summary", "module_a", "summary", source_port=port("south"), target_port=port("north", .2), waypoints=points((155, 500), (334, 500))),
        edge("b_summary", "module_b", "summary", source_port=port("south"), target_port=port("north")),
        edge("c_summary", "module_c", "summary", source_port=port("south"), target_port=port("north", .8), waypoints=points((705, 500), (526, 500)))]
    validation = dict(common, title="验证判断与修订回路", claim="求解输出按预先指定标准判断；失败进入模型修订并重新计算，成功输出验证报告。", canvas={"width": 900, "height": 660})
    validation["nodes"] = [header(validation["title"], 900),
        node("input", "模型与数据", "input", 265, 65, 320, 62),
        node("solve", "重新计算与输出", "process", 265, 185, 320, 65),
        node("decision", "验证通过？", "decision", 250, 320, 350, 150, condition_label="误差 ≤ 给定阈值"),
        node("revise", "检查与修订\n模型或数据", "process", 660, 360, 225, 70),
        node("report", "输出验证报告\n保存指标与残差", "output", 265, 580, 320, 70)]
    validation["edges"] = [edge("input_solve", "input", "solve"), edge("solve_decision", "solve", "decision"),
        edge("passed", "decision", "report", label="是", label_offset={"x": 28, "y": 0}),
        edge("failed", "decision", "revise", label="否", source_port=port("east"), target_port=port("west"), label_offset={"x": 0, "y": -20}),
        dict(edge("retry", "revise", "solve", source_port=port("north"), target_port=port("north"), waypoints=points((772.5, 155), (425, 155))), relation="feedback")]
    return {"research_roadmap": roadmap, "data_pipeline": pipeline, "model_structure": model, "validation_decision": validation}


def render_flows(output, font, drawio):
    from render_flowchart import prepare, render
    records = []
    for kind, spec in flow_contracts().items():
        prepare(spec)
        path = ROOT / "examples/flowcharts" / f"{kind}.json"
        save_json(path, spec)
        folder = output / kind
        report = render(path, folder, drawio=drawio, scale=3.5)
        thumb_path = HERE / f"{kind}.jpg"
        thumb = thumbnail(folder / "figure.png", thumb_path, font, kind=spec["title"])
        record = {"template_id": kind, "contract": str(path), "contract_sha256": sha(path),
                  "title": spec["title"], "output": str(folder), "render_status": report["status"],
                  "thumbnail": {"file": str(thumb_path), **thumb}, "inspection": report.get("inspection", {})}
        save_json(folder / "gallery-record.json", record)
        records.append(record)
        print(json.dumps({"template_id": kind, "status": report["status"], "thumbnail_bytes": thumb["bytes"]}, ensure_ascii=False), flush=True)
    path = ROOT / "examples/flowcharts/numerical_iteration.json"
    folder = output / "numerical-iteration"
    report = render(path, folder, drawio=drawio, scale=3.5)
    thumb_path = HERE / "numerical-iteration.jpg"
    thumb = thumbnail(folder / "figure.png", thumb_path, font, kind="数值迭代与时间推进", labelled=False)
    record = {"template_id": "numerical-iteration", "contract": str(path), "contract_sha256": sha(path),
              "title": "数值迭代与时间推进", "output": str(folder), "render_status": report["status"],
              "thumbnail": {"file": str(thumb_path), **thumb}, "inspection": report.get("inspection", {})}
    save_json(folder / "gallery-record.json", record)
    records.append(record)
    return records


def update_index(records):
    """Keep portable relative paths for gallery consumers; no personal data."""
    path = HERE / "gallery_assets.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        entries = {item["template_id"]: item for item in previous.get("records", [])}
    else:
        entries = {}
    relative = lambda value: Path(value).resolve().relative_to(ROOT).as_posix()
    for record in records:
        kind = record["template_id"]
        contract_path = Path(record["contract"])
        spec = json.loads(contract_path.read_text(encoding="utf-8"))
        is_chart = kind in IDS
        report_path = Path(record["outputs"]["png"]["file"]).parent / "figure-data.json" if is_chart else Path(record["output"]) / "rendering_report.json"
        thumb = dict(record["thumbnail"])
        thumb["file"] = relative(thumb["file"])
        thumb["source"] = relative(thumb["source"])
        entries[kind] = {"template_id": kind, "category": "statistical" if is_chart else "flowchart",
                         "title": TITLES.get(kind, record.get("title", spec["title"])),
                         "data_kind": spec["data_kind"], "contract": relative(contract_path),
                         "data": relative(contract_path.parent / spec["data"]) if is_chart else None,
                         "roles": spec.get("roles", {}), "axes": spec.get("axes", {}), "unit": spec.get("unit"),
                         "source_note": spec["source_note"], "generator": relative(__file__),
                         "thumbnail": thumb, "render_report": relative(report_path),
                         "generation_status": "generated_from_contract", "scientific_validation": "not established"}
    value = {"schema_version": 1, "seed": SEED,
             "source_scope": "Anonymous deterministic synthetic inputs and authored mechanism schematics; no contest results.",
             "generator": relative(__file__), "generator_sha256": sha(__file__),
             "records": list(entries.values())}
    save_json(path, value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="NEW directory, never overwrite figures")
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/simsun.ttc"))
    parser.add_argument("--drawio", type=Path, default=Path("E:/draw.io/draw.io.exe"))
    parser.add_argument("--only", choices=("all", "charts", "flowcharts"), default="all")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("--output must be a new directory")
    output.mkdir(parents=True)
    records = []
    if args.only in {"all", "charts"}:
        records.extend(render_charts(output, args.font))
    if args.only in {"all", "flowcharts"}:
        records.extend(render_flows(output, args.font, args.drawio))
    save_json(output / "gallery_assets.json", {"schema_version": 1, "seed": SEED, "records": records})
    update_index(records)
    print(json.dumps({"status": "generated", "records": len(records), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
