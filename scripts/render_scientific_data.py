"""Render selected scientific layouts from an explicit CSV contract, with computed metrics."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import numpy as np

SUPPORTED = {
    "correlation-pairgrid": "Selected numeric columns: distributions, scatter and Pearson correlation",
    "prediction-marginal-grid": "Observed/predicted rows with model, split and unique sample IDs",
    "rf-tpe-surface": "Complete observed parameter grid; no optimizer is run or inferred",
}
_FONT_CACHE = {}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(row: dict, key: str, line: int) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"CSV line {line}: {key} requires a numeric value") from exc
    if not np.isfinite(value):
        raise ValueError(f"CSV line {line}: {key} must be finite; clean data explicitly")
    return value


def regression_metrics(actual, predicted) -> dict:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.ndim != 1 or actual.shape != predicted.shape or len(actual) < 2:
        raise ValueError("Metrics require at least two aligned observations")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite observations")
    error = predicted - actual
    sse = float(np.sum(error ** 2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    result = {"n": len(actual), "rmse": float(np.sqrt(np.mean(error ** 2))),
              "mae": float(np.mean(np.abs(error))), "r2": None if sst == 0 else 1 - sse / sst}
    if any(value is not None and not np.isfinite(value) for value in result.values()):
        raise ValueError("Metric calculation exceeds finite numeric range")
    return result


def column(spec: dict) -> tuple[str, str]:
    if not isinstance(spec, dict) or not isinstance(spec.get("key"), str) or not spec["key"]:
        raise ValueError("Each numeric role requires a column key")
    label = spec.get("label")
    unit = spec.get("unit")
    if not isinstance(label, str) or not label.strip() or not isinstance(unit, str) or not unit.strip():
        raise ValueError("Each numeric role requires a nonempty label and unit (use 1 for dimensionless)")
    return spec["key"], f"{label}\n({unit})"


def prepare(manifest: Path) -> tuple[dict, dict, Path]:
    spec = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(spec, dict) or type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("Use figure contract schema_version 1")
    kind = spec.get("template_id")
    if not isinstance(kind, str) or kind not in SUPPORTED:
        raise ValueError("This data adapter supports: " + ", ".join(SUPPORTED))
    if not isinstance(spec.get("data_kind"), str) or spec["data_kind"] not in {"real", "synthetic"}:
        raise ValueError("Declare data_kind as real or synthetic; this declaration is not provenance proof")
    allowed = {"schema_version", "template_id", "data_kind", "data", "title", "source_note"} | {
        "correlation-pairgrid": {"columns"}, "prediction-marginal-grid": {"roles", "unit", "comparison"},
        "rf-tpe-surface": {"x", "y", "z", "surface_mode"}}[kind]
    if set(spec) - allowed:
        raise ValueError("Unsupported contract fields: " + ", ".join(sorted(set(spec) - allowed)))
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        raise ValueError("Figure title must be nonempty text")
    if "source_note" in spec and not isinstance(spec["source_note"], str):
        raise ValueError("source_note must be text")
    if not isinstance(spec.get("data"), str) or not spec["data"]:
        raise ValueError("Contract requires a CSV data path")
    source = (manifest.parent / spec["data"]).resolve(strict=True)
    if source.suffix.lower() != ".csv":
        raise ValueError("This adapter reads CSV; export the selected real fields explicitly")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requires unique column headings")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV has no observations")
    if any(None in row for row in rows):
        raise ValueError("CSV row has extra unnamed fields; correct the source structure explicitly")
    if kind == "correlation-pairgrid":
        roles = spec.get("columns")
        if not isinstance(roles, list) or not 2 <= len(roles) <= 9:
            raise ValueError("Select 2 to 9 numeric variables; split dense figures into meaningful groups")
        columns = [column(item) for item in roles]
        if len({key for key, _ in columns}) != len(columns):
            raise ValueError("Selected variables must be distinct")
        values = np.array([[numeric(row, key, i) for key, _ in columns] for i, row in enumerate(rows, 2)])
        if len(values) < 3 or (values.std(axis=0) == 0).any():
            raise ValueError("Pearson grid needs at least 3 observations and nonconstant variables")
        corr = np.corrcoef(values, rowvar=False)
        if not np.isfinite(corr).all():
            raise ValueError("Correlation calculation exceeds finite numeric range")
        bundle = {"values": values, "labels": [label for _, label in columns],
                  "statistics": {"n": len(values), "columns": [key for key, _ in columns],
                                 "correlation_method": "Pearson", "correlation": corr.tolist(),
                                 "fit_or_significance_test": "none", "standardized": False}}
    elif kind == "prediction-marginal-grid":
        roles = spec.get("roles")
        if not isinstance(roles, dict):
            raise ValueError("Prediction contract requires role mappings")
        for key in ("model", "split", "sample_id", "actual", "predicted"):
            if not isinstance(roles.get(key), str) or not roles[key]:
                raise ValueError(f"Missing prediction role: {key}")
        if set(roles) != {"model", "split", "sample_id", "actual", "predicted"} or len(set(roles.values())) != 5:
            raise ValueError("Map exactly five distinct prediction role columns")
        if not isinstance(spec.get("unit"), str) or not spec["unit"].strip():
            raise ValueError("Prediction contract requires the common actual/predicted unit")
        groups, seen, memberships, cohorts = {}, set(), {}, {}
        for i, row in enumerate(rows, 2):
            try:
                model, split, sample_id = (row[roles[key]] for key in ("model", "split", "sample_id"))
            except KeyError as exc:
                raise ValueError("Prediction role column is missing") from exc
            if not all(isinstance(v, str) and v.strip() for v in (model, split, sample_id)):
                raise ValueError(f"CSV line {i}: model/split/sample ID cannot be empty")
            key = model, split, sample_id
            if key in seen:
                raise ValueError("Duplicate model/split/sample ID; resolve duplicates explicitly")
            seen.add(key)
            membership = model, sample_id
            if membership in memberships and memberships[membership] != split:
                raise ValueError("A sample ID appears in multiple splits of one model")
            memberships[membership] = split
            actual, predicted = (numeric(row, roles[k], i) for k in ("actual", "predicted"))
            groups.setdefault(model, {}).setdefault(split, []).append((actual, predicted))
            cohorts.setdefault(model, {})[(split, sample_id)] = actual
        comparison = spec.get("comparison", True)
        if type(comparison) is not bool:
            raise ValueError("comparison must be a boolean")
        if comparison:
            first = next(iter(cohorts.values()))
            for other in cohorts.values():
                if other.keys() != first.keys() or any(not np.isclose(other[k], first[k], rtol=1e-12, atol=0) for k in first):
                    raise ValueError("Comparable model panels need the same sample IDs, splits and observed values")
        if len(groups) > 4 or any(len(parts) > 2 for parts in groups.values()):
            raise ValueError("Use at most four model panels and two splits; group a larger comparison")
        arrays = {model: {split: np.array(items) for split, items in parts.items()} for model, parts in groups.items()}
        stats = {model: {split: regression_metrics(items[:, 0], items[:, 1]) for split, items in parts.items()}
                 for model, parts in arrays.items()}
        bundle = {"groups": arrays, "statistics": {"metrics": stats, "comparison": comparison,
                    "kde": "Gaussian KDE with Silverman bandwidth; constant groups omit the curve"}}
    else:
        columns = [column(spec.get(key)) for key in ("x", "y", "z")]
        if len({key for key, _ in columns}) != 3:
            raise ValueError("Surface axes and response need distinct columns")
        values = np.array([[numeric(row, key, i) for key, _ in columns] for i, row in enumerate(rows, 2)])
        mode = spec.get("surface_mode", "grid")
        if not isinstance(mode, str) or mode not in {"grid", "scatter"}:
            raise ValueError("surface_mode must be grid or scatter")
        if mode == "scatter":
            if len(values) < 2:
                raise ValueError("A trial-point plot needs at least two observations")
            return spec, {"values": values, "mode": mode, "labels": [label for _, label in columns],
                          "statistics": {"samples": len(values), "minimum": float(values[:, 2].min()),
                                         "maximum": float(values[:, 2].max()), "optimizer_run_by_renderer": False,
                                         "surface": "supplied trial points only; no interpolation"}}, source
        x, y = np.unique(values[:, 0]), np.unique(values[:, 1])
        positions = {(a, b): c for a, b, c in values}
        if len(positions) != len(values):
            raise ValueError("Duplicate grid coordinates; choose and record an aggregation before plotting")
        if len(x) < 2 or len(y) < 2 or len(positions) != len(x) * len(y):
            raise ValueError("Surface requires a complete rectangular grid; use a scatter plot for sparse trials")
        z = np.array([[positions[(a, b)] for a in x] for b in y])
        bundle = {"x": x, "y": y, "z": z, "mode": mode, "labels": [label for _, label in columns],
                  "statistics": {"samples": len(values), "grid_shape": list(z.shape), "minimum": float(z.min()),
                                 "maximum": float(z.max()), "optimizer_run_by_renderer": False,
                                 "surface": "faces connect supplied grid nodes; no analytical blending or fitted objective"}}
    return spec, bundle, source


def density(values, grid):
    std = float(np.std(values, ddof=1))
    if std == 0:
        return None
    iqr = float(np.subtract(*np.percentile(values, [75, 25])))
    scale = min(std, iqr / 1.34) if iqr > 0 else std
    bandwidth = 0.9 * scale * len(values) ** (-0.2)
    z = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * z ** 2).mean(axis=1) / (bandwidth * np.sqrt(2 * np.pi))


def register_font(font: Path, output: Path, font_manager) -> tuple[str, dict]:
    """Resolve variable weights locally so Matplotlib does not use a thin default."""
    from fontTools.ttLib import TTFont
    source = font.resolve(strict=True)
    source_hash = digest(source)
    key = str(source), source_hash
    cached = _FONT_CACHE.get(key)
    if cached and all(path.is_file() for path in cached[2]):
        return cached[0], cached[1]
    if cached:
        old_paths = {str(path) for path in cached[2]}
        font_manager.fontManager.ttflist = [entry for entry in font_manager.fontManager.ttflist if entry.fname not in old_paths]
    with TTFont(source, fontNumber=0) as face:
        axis = next((a for a in face["fvar"].axes if a.axisTag == "wght"), None) if "fvar" in face else None
        weights = [max(axis.minValue, min(weight, axis.maxValue)) for weight in (400, 700)] if axis else []
    paths = []
    if weights:
        from fontTools.varLib.instancer import instantiateVariableFont
        folder = output / ".fonts"
        folder.mkdir()
        for weight in dict.fromkeys(weights):
            with TTFont(source) as variable:
                static = instantiateVariableFont(variable, {"wght": weight}, inplace=True, updateFontNames=True)
                path = folder / f"weight-{int(weight)}.ttf"
                static.save(path)
                paths.append(path)
        license_file = source.parent / "OFL.txt"
        if license_file.is_file():
            shutil.copy2(license_file, folder / "OFL.txt")
    else:
        paths = [source]
    for path in paths:
        font_manager.fontManager.addfont(str(path))
    family = font_manager.FontProperties(fname=str(paths[0])).get_name()
    record = {"source_sha256": source_hash, "variable_weights_instantiated": weights,
              "family": family, "source_modified": False, "installed_systemwide": False}
    _FONT_CACHE[key] = family, record, paths
    return family, record


def render(manifest: Path, output: Path, font: Path | None = None) -> dict:
    if output.is_symlink() or output.exists():
        raise ValueError("Use a new output directory; existing figures are preserved")
    spec, bundle, source = prepare(manifest)
    source_hash, manifest_hash = digest(source), digest(manifest)
    renderer_hash = digest(Path(__file__))
    output.mkdir(parents=True)
    os.environ["MPLCONFIGDIR"] = str(output / ".mplconfig")
    import matplotlib as mpl
    mpl.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    if font is not None:
        family, font_record = register_font(font, output, font_manager)
    else:
        family, font_record = "DejaVu Sans", {"family": "DejaVu Sans"}
    mpl.rcParams.update({"font.family": family, "font.size": 8, "axes.labelsize": 8,
                         "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.linewidth": .65,
                         "svg.fonttype": "none", "pdf.fonttype": 42, "axes.unicode_minus": False})
    kind = spec["template_id"]
    if kind == "correlation-pairgrid":
        values, labels, corr = bundle["values"], bundle["labels"], np.array(bundle["statistics"]["correlation"])
        count = len(labels)
        fig, axes = plt.subplots(count, count, figsize=(6.3, 6.1), squeeze=False)
        for row in range(count):
            for col in range(count):
                ax = axes[row, col]
                if row > col:
                    ax.scatter(values[:, col], values[:, row], s=5, color="#167d8d", alpha=.42, linewidths=0)
                elif row == col:
                    ax.hist(values[:, col], bins=15, color="#aad5df", edgecolor="white", linewidth=.5)
                else:
                    ax.set_facecolor(mpl.colormaps["RdBu_r"]((corr[row, col] + 1) / 2))
                    ax.text(.5, .5, f"{corr[row, col]:.2f}", transform=ax.transAxes, ha="center", va="center",
                            fontsize=9, color="white" if abs(corr[row, col]) > .6 else "#243746", weight="bold")
                    ax.set_xticks([]); ax.set_yticks([])
                if row == count - 1:
                    ax.set_xlabel(labels[col])
                elif row >= col:
                    ax.tick_params(labelbottom=False)
                if col == 0:
                    ax.set_ylabel("Count" if row == col else labels[row])
                elif row >= col:
                    ax.tick_params(labelleft=False)
                ax.spines[["top", "right"]].set_visible(False)
        fig.subplots_adjust(left=.13, right=.98, bottom=.13, top=.88, wspace=.24, hspace=.22)
    elif kind == "prediction-marginal-grid":
        models = list(bundle["groups"])
        width = 2 if len(models) > 1 else 1
        height = int(np.ceil(len(models) / width))
        fig = plt.figure(figsize=(6.3, 3.45 * height))
        outer = fig.add_gridspec(height, width, left=.1, right=.98, bottom=.14 / height, top=.8 if height == 1 else .89,
                                wspace=.30, hspace=.55)
        colors = ["#168c9a", "#e49c45", "#7862a1", "#ce6e7b"]
        all_pooled = np.concatenate([values.ravel() for parts in bundle["groups"].values() for values in parts.values()])
        for index, model in enumerate(models):
            grid = outer[index // width, index % width].subgridspec(2, 2, height_ratios=[.24, 1], width_ratios=[1, .24], hspace=.03, wspace=.03)
            main = fig.add_subplot(grid[1, 0]); top = fig.add_subplot(grid[0, 0], sharex=main); side = fig.add_subplot(grid[1, 1], sharey=main)
            items = bundle["groups"][model]
            pooled = all_pooled if bundle["statistics"]["comparison"] else np.concatenate(list(items.values())).ravel()
            span = float(np.ptp(pooled)); pad = .08 * span if span else max(abs(pooled[0]) * .1, 1)
            limits = float(pooled.min() - pad), float(pooled.max() + pad)
            curve_grid = np.linspace(*limits, 160)
            bins = np.linspace(*limits, 17)
            main.plot(limits, limits, ls="--", color="#8a99a8", lw=.8)
            metrics = []
            for color, (split, values) in zip(colors, items.items()):
                main.scatter(values[:, 0], values[:, 1], s=8, facecolors="none", edgecolors=color, lw=.6, alpha=.6, label=split)
                top.hist(values[:, 0], bins=bins, density=True, color=color, alpha=.16, histtype="stepfilled")
                side.hist(values[:, 1], bins=bins, density=True, color=color, alpha=.16, orientation="horizontal", histtype="stepfilled")
                for array, marginal, horizontal in [(values[:, 0], top, False), (values[:, 1], side, True)]:
                    kde = density(array, curve_grid)
                    if kde is not None:
                        marginal.plot(kde, curve_grid, color=color, lw=.8) if horizontal else marginal.plot(curve_grid, kde, color=color, lw=.8)
                stats = bundle["statistics"]["metrics"][model][split]
                r2 = "NA" if stats["r2"] is None else f"{stats['r2']:.3f}"
                metrics.append(f"{split}: n={stats['n']}, R²={r2}, RMSE={stats['rmse']:.3g}")
            main.set(xlim=limits, ylim=limits, xlabel=f"Observed ({spec['unit']})", ylabel=f"Predicted ({spec['unit']})")
            main.legend(fontsize=6, loc="upper left", frameon=False)
            top.set_title(model, fontsize=9, weight="bold")
            main.text(0, -.31, "\n".join(metrics), transform=main.transAxes, fontsize=6.5, va="top")
            top.tick_params(labelbottom=False, left=False, labelleft=False); side.tick_params(labelleft=False, bottom=False, labelbottom=False)
            for ax in (main, top, side):
                ax.spines[["top", "right"]].set_visible(False)
    else:
        fig = plt.figure(figsize=(6.3, 4.5))
        ax = fig.add_subplot(projection="3d")
        if bundle["mode"] == "grid":
            x, y = np.meshgrid(bundle["x"], bundle["y"])
            surface = ax.plot_surface(x, y, bundle["z"], cmap="coolwarm", edgecolor="white", linewidth=.15,
                                      antialiased=True, rcount=len(bundle["y"]), ccount=len(bundle["x"]))
            ax.scatter(x, y, bundle["z"], s=4, color="#243746", depthshade=False)
        else:
            points = bundle["values"]
            surface = ax.scatter(points[:, 0], points[:, 1], points[:, 2], c=points[:, 2], cmap="coolwarm", s=16, depthshade=False)
        ax.set(xlabel=bundle["labels"][0], ylabel=bundle["labels"][1], zlabel=bundle["labels"][2])
        ax.view_init(elev=26, azim=-55)
        colorbar = fig.colorbar(surface, ax=ax, shrink=.55, pad=.12, label=bundle["labels"][2])
        if colorbar.solids is not None:
            colorbar.solids.set_rasterized(False)
        fig.subplots_adjust(left=0, right=.98, bottom=.05, top=.85)
    title = spec.get("title", kind)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Figure title must be nonempty text")
    fig.suptitle(title, fontsize=11, weight="bold", y=.98)
    if spec["data_kind"] == "synthetic":
        banner = "合成数据示例 / SYNTHETIC DATA" if font else "SYNTHETIC DATA"
        fig.text(.5, .925, banner, ha="center", va="top", fontsize=8, color="#9e543b")
    outputs = {}
    for suffix in ("png", "pdf", "svg"):
        path = output / ("figure." + suffix)
        fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
        outputs[suffix] = {"file": path.name, "sha256": digest(path)}
    plt.close(fig)
    if digest(source) != source_hash or digest(manifest) != manifest_hash or digest(Path(__file__)) != renderer_hash:
        raise ValueError("Input or renderer changed during drawing; reject these outputs and rerun from stable sources")
    # Preserve inputs and an original editable renderer; no upstream code is redistributed.
    reproduce = output / "reproduce"
    reproduce.mkdir()
    shutil.copy2(source, reproduce / "data.csv")
    copy_spec = dict(spec, data="data.csv")
    (reproduce / "contract.json").write_text(json.dumps(copy_spec, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(Path(__file__), reproduce / "render_scientific_data.py")
    report = {"schema_version": 1, "template_id": kind, "data_kind": spec["data_kind"],
              "implementation": "original project data adapter; upstream style references are separate",
              "source_note": spec.get("source_note", ""),
              "font": font_record,
              "input_sha256": source_hash, "contract_sha256": manifest_hash, "renderer_sha256": renderer_hash,
              "numpy_version": np.__version__, "matplotlib_version": mpl.__version__,
              "statistics": bundle["statistics"], "outputs": outputs,
              "scope": "Declared CSV data and figure calculations; not data authenticity, model training or paper acceptance"}
    (output / "figure-data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true", help="Check selected data roles and compute statistics without drawing")
    parser.add_argument("--font", type=Path, help="Optional existing CJK font file")
    args = parser.parse_args(argv)
    if args.output is None and not args.validate_only:
        parser.error("--output is required unless --validate-only is selected")
    try:
        if args.validate_only:
            spec, bundle, source = prepare(args.manifest)
            print(json.dumps({"template_id": spec["template_id"], "data_kind": spec["data_kind"],
                              "input_sha256": digest(source), "statistics": bundle["statistics"]}, ensure_ascii=False, allow_nan=False))
            return 0
        report = render(args.manifest, args.output, args.font)
        print(json.dumps({"template_id": report["template_id"], "data_kind": report["data_kind"], "outputs": report["outputs"]}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
