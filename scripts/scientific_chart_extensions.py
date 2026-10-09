"""Original CSV chart adapters; supplied observations only, no model fitting.

``prepare_extension`` checks explicit column roles and computes inspectable
statistics. ``render_extension`` consumes that checked bundle and returns a
Matplotlib Figure. The calling renderer owns fonts, provenance and export.
"""
from __future__ import annotations

import hashlib
import json
from statistics import NormalDist
import numpy as np


def _metadata(description, roles, axes=(), unit=False, required_fields=(), optional_fields=()):
    return {"description": description, "roles": list(roles), "axes": list(axes),
            "unit": unit, "required_fields": list(required_fields),
            "optional_fields": list(optional_fields)}


EXTENSIONS = {
    "grouped-line": _metadata("Ordered supplied observations by group; no interpolation model", ("group", "x", "y"), ("x", "y")),
    "uncertainty-band": _metadata("Supplied point estimates and named lower/upper intervals", ("group", "x", "estimate", "lower", "upper"), ("x", "estimate"), required_fields=("interval_note",)),
    "grouped-scatter": _metadata("Independent identified observations by group; no fitted trend", ("group", "sample_id", "x", "y"), ("x", "y")),
    "grouped-box": _metadata("Raw identified observations, quartiles and Tukey box geometry", ("group", "sample_id", "value"), unit=True),
    "grouped-violin": _metadata("Raw observations with descriptive Gaussian KDE; constants shown as points", ("group", "sample_id", "value"), unit=True),
    "distribution-histogram": _metadata("Shared explicit histogram edges for raw grouped observations", ("group", "sample_id", "value"), unit=True, optional_fields=("bins",)),
    "ecdf-distribution": _metadata("Empirical cumulative distribution of supplied observations", ("group", "sample_id", "value"), unit=True),
    "grouped-bar": _metadata("Complete category/series table of supplied aggregate values", ("category", "series", "value"), unit=True),
    "stacked-bar": _metadata("Complete nonnegative category/series table of supplied components", ("category", "series", "value"), unit=True),
    "matrix-heatmap": _metadata("Complete supplied row/column matrix; no missing-cell imputation", ("row", "column", "value"), unit=True),
    "residual-diagnostics": _metadata("Comparable identified observed/predicted cohorts with residual diagnostics", ("model", "split", "sample_id", "actual", "predicted"), ("actual", "predicted")),
    "binary-pr-comparison": _metadata("Empirical precision/recall and average precision on a shared cohort", ("model", "sample_id", "label", "score")),
    "confusion-matrix": _metadata("Supplied categorical predictions on a shared identified cohort", ("model", "sample_id", "actual", "predicted"), optional_fields=("classes",)),
    "optimization-convergence": _metadata("Supplied objective values indexed by observed iteration; no optimizer run", ("group", "iteration", "objective"), ("iteration", "objective")),
    "pareto-front": _metadata("Nondominated supplied candidates under two explicitly directed objectives", ("group", "sample_id", "x", "y"), ("x", "y"), required_fields=("x_direction", "y_direction")),
}

NEW_EXTENSIONS = {
    "hexbin-density": _metadata("Hexagonal counts from identified supplied points; no fitted density", ("sample_id", "x", "y"), ("x", "y"), optional_fields=("gridsize",)),
    "density-contour": _metadata("Descriptive contours of an explicit rectangular histogram density; no KDE or spatial interpolation", ("sample_id", "x", "y"), ("x", "y"), required_fields=("density_method",), optional_fields=("bins",)),
    "coefficient-forest": _metadata("Supplied coefficient estimates and named intervals; no regression fitted", ("term", "estimate", "lower", "upper"), ("estimate",), required_fields=("interval_note",), optional_fields=("reference_value",)),
    "sensitivity-tornado": _metadata("Supplied low/high scenario outcomes relative to a common baseline; no scenarios run", ("parameter", "baseline", "lower_case", "upper_case"), ("baseline",), required_fields=("scenario_note",)),
    "multimetric-profile": _metadata("Complete metric profiles on an explicitly supplied common scale; no hidden normalization", ("series", "metric", "value"), unit=True, required_fields=("scale_min", "scale_max", "scale_note")),
    "bubble-matrix": _metadata("Complete nonnegative matrix with circle areas proportional to supplied values", ("row", "column", "value"), unit=True),
    "ridge-distribution": _metadata("Identified grouped raw observations and descriptive Gaussian KDE on a common axis", ("group", "sample_id", "value"), unit=True),
    "qq-normal": _metadata("Ordered raw observations against standard-normal quantiles; no normality test", ("group", "sample_id", "value"), unit=True),
    "calibration-curve": _metadata("Empirical binary calibration using explicit probability bin edges and shared labeled samples", ("model", "sample_id", "label", "score"), required_fields=("bin_edges",)),
    "spatial-point-values": _metadata("Supplied point coordinates and values; no basemap, projection or spatial interpolation", ("sample_id", "x", "y", "value"), ("x", "y", "value"), required_fields=("coordinate_system",)),
}
EXTENSIONS.update(NEW_EXTENSIONS)

COLORS = ("#168c9a", "#e49c45", "#7862a1", "#ce6e7b", "#527c48", "#5e789d", "#a56d40", "#499984")


def _number(row, key, line):
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"CSV line {line}: {key} requires a numeric value") from exc
    if not np.isfinite(value):
        raise ValueError(f"CSV line {line}: {key} must be finite")
    return value


def _text(row, key, line):
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CSV line {line}: {key} requires nonempty text")
    if value != value.strip():
        raise ValueError(f"CSV line {line}: {key} has surrounding whitespace; clean labels explicitly")
    return value


def _contract(spec, rows):
    if (not isinstance(spec, dict) or not isinstance(spec.get("template_id"), str)
            or spec["template_id"] not in EXTENSIONS):
        raise ValueError("Unknown scientific chart extension")
    kind = spec["template_id"]
    meta = EXTENSIONS[kind]
    allowed = {"schema_version", "template_id", "data_kind", "data", "title", "source_note", "roles"}
    if meta["axes"]:
        allowed.add("axes")
    if meta["unit"]:
        allowed.add("unit")
    allowed.update(meta["required_fields"] + meta["optional_fields"])
    if set(spec) - allowed:
        raise ValueError("Unsupported contract fields: " + ", ".join(sorted(set(spec) - allowed)))
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("Use chart schema_version 1")
    if not isinstance(spec.get("data_kind"), str) or spec["data_kind"] not in {"real", "synthetic"}:
        raise ValueError("Declare data_kind as real or synthetic")
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        raise ValueError("Figure title must be nonempty text")
    if "source_note" in spec and not isinstance(spec["source_note"], str):
        raise ValueError("source_note must be text")
    roles = spec.get("roles")
    if (not isinstance(roles, dict) or set(roles) != set(meta["roles"])
            or not all(isinstance(key, str) and key.strip() for key in roles.values())
            or len(set(roles.values())) != len(roles)):
        raise ValueError("Map exactly these distinct role columns: " + ", ".join(meta["roles"]))
    if not isinstance(rows, list) or not rows:
        raise ValueError("CSV has no observations")
    if any(not isinstance(row, dict) or None in row or not set(roles.values()).issubset(row) for row in rows):
        raise ValueError("CSV role column is missing or row contains unnamed extra fields")
    axes = spec.get("axes", {})
    if meta["axes"]:
        if not isinstance(axes, dict) or set(axes) != set(meta["axes"]):
            raise ValueError("Map exactly these numeric axes: " + ", ".join(meta["axes"]))
        for role, axis in axes.items():
            if (not isinstance(axis, dict) or set(axis) != {"label", "unit"}
                    or not all(isinstance(axis[key], str) and axis[key].strip() for key in ("label", "unit"))):
                raise ValueError(f"Axis {role} needs a label and unit (use 1 for dimensionless)")
    if meta["unit"] and (not isinstance(spec.get("unit"), str) or not spec["unit"].strip()):
        raise ValueError("Contract requires a common measurement unit")
    for field in meta["required_fields"]:
        if field in {"scale_min", "scale_max", "bin_edges"}:
            if field not in spec:
                raise ValueError(f"Contract requires {field}")
            continue
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            raise ValueError(f"Contract requires {field}")
    return kind, roles


def _summary(values):
    values = np.asarray(values, dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        result = {"n": len(values), "mean": float(values.mean()), "median": float(np.median(values)),
                  "sd": None if len(values) < 2 else float(values.std(ddof=1)),
                  "q1": float(np.percentile(values, 25)), "q3": float(np.percentile(values, 75)),
                  "minimum": float(values.min()), "maximum": float(values.max())}
    return result


def _finite_statistics(stats):
    def walk(value):
        if isinstance(value, dict):
            return all(walk(child) for child in value.values())
        if isinstance(value, (tuple, list)):
            return all(walk(child) for child in value)
        if isinstance(value, (float, np.floating)):
            return bool(np.isfinite(value))
        return True
    if not walk(stats):
        raise ValueError("Statistical calculation exceeds finite numeric range")
    # Ensure metadata remains directly serializable by the provenance renderer.
    json.dumps(stats, allow_nan=False)


def _limit(groups, maximum=8):
    if not 1 <= len(groups) <= maximum:
        raise ValueError(f"Use one to {maximum} groups; split a denser comparison")


def _identified_groups(rows, roles, values):
    groups, memberships = {}, {}
    for line, row in enumerate(rows, 2):
        group = _text(row, roles["group"], line)
        sample_id = _text(row, roles["sample_id"], line)
        if sample_id in memberships:
            raise ValueError("Duplicate or cross-group sample ID; use explicit paired-data adapters for repeated samples")
        memberships[sample_id] = group
        groups.setdefault(group, []).append((sample_id, *[_number(row, roles[value], line) for value in values]))
    _limit(groups)
    return groups


def empirical_pr(labels, scores):
    """Threshold PR with simultaneous ties; AP is recall-increment weighting."""
    labels, scores = np.asarray(labels, dtype=float), np.asarray(scores, dtype=float)
    if labels.ndim != 1 or scores.shape != labels.shape or not len(labels):
        raise ValueError("PR requires nonempty aligned label and score vectors")
    if not np.isfinite(labels).all() or not np.isfinite(scores).all() or not np.isin(labels, [0, 1]).all():
        raise ValueError("PR requires finite scores and binary 0/1 labels")
    positives, n = int(labels.sum()), len(labels)
    if positives == 0 or positives == n:
        raise ValueError("PR requires both positive and negative classes")
    order = np.argsort(-scores, kind="mergesort")
    ranked_labels, ranked_scores = labels[order], scores[order]
    ends = np.r_[np.flatnonzero(ranked_scores[1:] != ranked_scores[:-1]), n - 1]
    tp = np.cumsum(ranked_labels)[ends]
    precision, recall = tp / (ends + 1), tp / positives
    ap = float(np.sum(np.diff(np.r_[0., recall]) * precision))
    return {"n": n, "positive_count": positives, "negative_count": n - positives,
            "prevalence": positives / n, "positive_label": 1, "average_precision": ap,
            "recall": [0.] + recall.tolist(), "precision": [1.] + precision.tolist(),
            "thresholds": [None] + ranked_scores[ends].tolist(),
            "threshold_rule": "score >= threshold; equal scores move together; initial None is above all scores",
            "average_precision_method": "sum of recall increments times precision after each tied threshold group; not trapezoidal area"}


def _nondominated_minima(points):
    """Two-objective Pareto membership in O(n log n), preserving tied points."""
    order = np.argsort(points[:, 0], kind="mergesort")
    sorted_points = points[order]
    ends = np.r_[np.flatnonzero(sorted_points[1:, 0] != sorted_points[:-1, 0]) + 1, len(points)]
    result, start, best_y = np.zeros(len(points), dtype=bool), 0, float("inf")
    for end in ends:
        group = sorted_points[start:end]
        group_minimum = float(group[:, 1].min())
        # A strictly smaller x with equal y dominates; equal x/equal y do not.
        if group_minimum < best_y:
            result[order[start:end][group[:, 1] == group_minimum]] = True
        best_y = min(best_y, group_minimum)
        start = int(end)
    return result


def _cohort(rows, roles, mode):
    groups = {}
    memberships = {}
    for line, row in enumerate(rows, 2):
        model, sample_id = (_text(row, roles[key], line) for key in ("model", "sample_id"))
        split = _text(row, roles["split"], line) if "split" in roles else None
        key = (split, sample_id) if split is not None else sample_id
        samples = groups.setdefault(model, {})
        if key in samples:
            raise ValueError("Duplicate model/split/sample ID")
        membership = model, sample_id
        if membership in memberships and memberships[membership] != split:
            raise ValueError("A sample ID appears in multiple splits of one model")
        memberships[membership] = split
        if mode == "categorical":
            pair = tuple(_text(row, roles[key], line) for key in ("actual", "predicted"))
        elif mode == "pr":
            pair = tuple(_number(row, roles[key], line) for key in ("label", "score"))
            if pair[0] not in {0, 1}:
                raise ValueError("PR labels must be binary 0/1")
        else:
            pair = tuple(_number(row, roles[key], line) for key in ("actual", "predicted"))
        samples[key] = pair
    _limit(groups, 6 if mode == "pr" else 4)
    if mode == "pr" and len(groups) < 2:
        raise ValueError("PR comparison requires at least two models")
    reference = next(iter(groups.values()))
    for samples in groups.values():
        same_keys = samples.keys() == reference.keys()
        same_truth = same_keys and all(samples[key][0] == reference[key][0] for key in reference)
        if not same_truth:
            raise ValueError("Comparable models require the same cohort sample IDs, splits and observed labels/values")
    return groups


def prepare_extension(spec, rows):
    """Validate role-mapped CSV records and return checked plotting arrays/statistics."""
    kind, roles = _contract(spec, rows)
    stats = {"observations": len(rows), "fit_or_significance_test": "none",
             "confidence_interval_calculated": False, "missing_values_imputed": False}
    if kind in NEW_EXTENSIONS:
        bundle = _prepare_new(spec, rows, roles, stats)
        bundle["statistics"] = stats
        _finite_statistics(stats)
        return bundle
    if kind in {"grouped-line", "uncertainty-band", "optimization-convergence"}:
        x_role, value_roles = (("iteration", ("objective",)) if kind == "optimization-convergence" else
                               ("x", ("estimate", "lower", "upper")) if kind == "uncertainty-band" else ("x", ("y",)))
        groups, seen = {}, set()
        for line, row in enumerate(rows, 2):
            group = _text(row, roles["group"], line)
            x = _number(row, roles[x_role], line)
            if kind == "optimization-convergence" and (x < 0 or not x.is_integer()):
                raise ValueError("Observed iteration must be a nonnegative integer")
            if (group, x) in seen:
                raise ValueError("Duplicate group/x or group/iteration coordinate; aggregate explicitly before plotting")
            seen.add((group, x))
            values = [_number(row, roles[value], line) for value in value_roles]
            if kind == "uncertainty-band" and not values[1] <= values[0] <= values[2]:
                raise ValueError("Supplied lower <= estimate <= upper is required; intervals may not be reversed")
            groups.setdefault(group, []).append((x, *values))
        _limit(groups)
        if any(len(group) < 2 for group in groups.values()):
            raise ValueError("Each line group needs at least two supplied coordinates")
        arrays = {group: np.array(sorted(values), dtype=float) for group, values in groups.items()}
        stats["groups"] = {group: {"n": len(values), "x_minimum": float(values[:, 0].min()),
                                  "x_maximum": float(values[:, 0].max()), "value_summary": _summary(values[:, 1])}
                           for group, values in arrays.items()}
        stats["connections"] = "straight segments between supplied observations in ascending x order"
        if kind == "uncertainty-band":
            stats["interval_note"] = spec["interval_note"]
            stats["intervals"] = "provided lower/upper values; not calculated or certified as confidence intervals"
        if kind == "optimization-convergence":
            stats["optimizer_run_by_renderer"] = False
            stats["scope"] = "supplied iteration/objective observations; monotonic convergence is not assumed"
        bundle = {"groups": arrays}
    elif kind in {"grouped-scatter", "pareto-front"}:
        groups = _identified_groups(rows, roles, ("x", "y"))
        arrays = {group: np.array([item[1:] for item in values], dtype=float) for group, values in groups.items()}
        stats["groups"] = {group: {"n": len(values), "x": _summary(values[:, 0]), "y": _summary(values[:, 1])}
                           for group, values in arrays.items()}
        bundle = {"groups": arrays, "sample_ids": {group: [item[0] for item in values] for group, values in groups.items()}}
        if kind == "pareto-front":
            for role in ("x", "y"):
                if spec[role + "_direction"] not in {"min", "max"}:
                    raise ValueError("Pareto x_direction and y_direction must each be min or max")
            points = np.concatenate(list(arrays.values()))
            ids = [item[0] for values in groups.values() for item in values]
            signed = points * np.array([1 if spec[role + "_direction"] == "min" else -1 for role in ("x", "y")])
            nondominated = _nondominated_minima(signed)
            bundle["front"] = points[nondominated]
            stats.update({"x_direction": spec["x_direction"], "y_direction": spec["y_direction"],
                          "nondominated_sample_ids": [sample_id for sample_id, flag in zip(ids, nondominated) if flag],
                          "nondominated_count": int(nondominated.sum()), "optimizer_run_by_renderer": False,
                          "scope": "nondominated among supplied candidates only; no continuous or global-optimum claim"})
    elif kind in {"grouped-box", "grouped-violin", "distribution-histogram", "ecdf-distribution"}:
        groups = _identified_groups(rows, roles, ("value",))
        if any(len(values) < 2 for values in groups.values()):
            raise ValueError("Each distribution group needs at least two identified observations")
        arrays = {group: np.array([item[1] for item in values]) for group, values in groups.items()}
        stats["groups"] = {group: _summary(values) for group, values in arrays.items()}
        bundle = {"groups": arrays, "sample_ids": {group: [item[0] for item in values] for group, values in groups.items()}}
        if kind == "distribution-histogram":
            bins = spec.get("bins", 15)
            if type(bins) is not int or not 1 <= bins <= 60:
                raise ValueError("Histogram bins must be an integer from 1 to 60")
            pooled = np.concatenate(list(arrays.values()))
            counts, edges = np.histogram(pooled, bins=bins)
            if not np.isfinite(edges).all() or (np.diff(edges) <= 0).any():
                raise ValueError("Histogram edges exceed numeric range or resolution")
            bundle["edges"] = edges
            stats["histogram"] = {"edges": edges.tolist(), "group_counts": {
                group: np.histogram(values, bins=edges)[0].tolist() for group, values in arrays.items()},
                "normalization": "observation count; common edges for all groups"}
        if kind == "ecdf-distribution":
            curves = {}
            for group, values in arrays.items():
                unique, counts = np.unique(values, return_counts=True)
                curves[group] = {"value": unique.tolist(), "probability": (np.cumsum(counts) / len(values)).tolist()}
            bundle["curves"] = curves
            stats["ecdf"] = curves
            stats["ecdf_definition"] = "F(x) = number of supplied observations <= x / n; ties combined"
        if kind == "grouped-violin":
            stats["kde"] = "Gaussian KDE with Silverman bandwidth; constant groups omit density and show raw points"
            stats["constant_groups"] = [group for group, values in arrays.items() if np.ptp(values) == 0]
        if kind == "grouped-box":
            stats["box_geometry"] = "linear sample quartiles; whiskers at supplied points within 1.5 IQR; outliers displayed"
    elif kind in {"grouped-bar", "stacked-bar", "matrix-heatmap"}:
        row_role, col_role = ("row", "column") if kind == "matrix-heatmap" else ("category", "series")
        first, second, values = [], [], {}
        for line, row in enumerate(rows, 2):
            a, b = _text(row, roles[row_role], line), _text(row, roles[col_role], line)
            if (a, b) in values:
                raise ValueError("Duplicate matrix/category-series cell; choose aggregation explicitly")
            value = _number(row, roles["value"], line)
            if kind == "stacked-bar" and value < 0:
                raise ValueError("Stacked components must be nonnegative")
            values[a, b] = value
            if a not in first:
                first.append(a)
            if b not in second:
                second.append(b)
        maximum = 20 if kind == "matrix-heatmap" else 12
        if len(first) > maximum or len(second) > (maximum if kind == "matrix-heatmap" else 8):
            raise ValueError("Matrix/category-series table is too dense; select meaningful groups")
        if len(values) != len(first) * len(second):
            raise ValueError("A complete matrix/category-series table is required; missing cells are not zero")
        matrix = np.array([[values[a, b] for b in second] for a in first])
        stats.update({"row_labels": first, "column_labels": second, "matrix": matrix.tolist(),
                      "input_aggregation": "supplied cells; renderer does not aggregate observations"})
        bundle = {"rows": first, "columns": second, "matrix": matrix}
        if kind == "stacked-bar":
            with np.errstate(over="ignore", invalid="ignore"):
                totals = matrix.sum(axis=1)
            stats["category_totals"] = dict(zip(first, totals.tolist()))
    elif kind == "residual-diagnostics":
        if spec["axes"]["actual"]["unit"] != spec["axes"]["predicted"]["unit"]:
            raise ValueError("Observed and predicted values need the same unit for residuals")
        cohorts = _cohort(rows, roles, "regression")
        arrays = {}
        for model, samples in cohorts.items():
            splits = {}
            for (split, sample_id), pair in samples.items():
                splits.setdefault(split, []).append(pair)
            if len(splits) > 2 or any(len(values) < 2 for values in splits.values()):
                raise ValueError("Residual panels require at least two samples per split and at most two splits")
            arrays[model] = {split: np.array(values) for split, values in splits.items()}
        metrics = {}
        for model, splits in arrays.items():
            metrics[model] = {}
            for split, values in splits.items():
                with np.errstate(over="ignore", invalid="ignore"):
                    residual = values[:, 1] - values[:, 0]
                    sse, sst = np.sum(residual ** 2), np.sum((values[:, 0] - values[:, 0].mean()) ** 2)
                    metrics[model][split] = {"n": len(values), "rmse": float(np.sqrt(np.mean(residual ** 2))),
                                             "mae": float(np.mean(np.abs(residual))), "bias": float(residual.mean()),
                                             "r2": None if sst == 0 else float(1 - sse / sst),
                                             "residual_summary": _summary(residual)}
        stats.update({"metrics": metrics, "same_cohort_verified": True,
                      "residual_direction": "predicted - observed", "model_fit_by_renderer": False,
                      "scope": "descriptive residuals of supplied predictions; no normality test or generalization inference"})
        bundle = {"groups": arrays}
    elif kind == "binary-pr-comparison":
        cohorts = _cohort(rows, roles, "pr")
        curves = {model: empirical_pr([pair[0] for pair in samples.values()], [pair[1] for pair in samples.values()])
                  for model, samples in cohorts.items()}
        stats.update({"models": curves, "same_cohort_verified": True,
                      "training_run_by_renderer": False, "cross_validation": "none; one supplied score per model/sample"})
        bundle = {"curves": curves}
    else:  # confusion-matrix
        cohorts = _cohort(rows, roles, "categorical")
        observed = {label for samples in cohorts.values() for pair in samples.values() for label in pair}
        classes = spec.get("classes", sorted(observed))
        if (not isinstance(classes, list) or not 2 <= len(classes) <= 15
                or not all(isinstance(value, str) and value.strip() and value == value.strip() for value in classes)
                or len(set(classes)) != len(classes) or not observed.issubset(classes)):
            raise ValueError("classes must be two to fifteen distinct labels covering all observed and predicted labels")
        indices = {label: index for index, label in enumerate(classes)}
        matrices, metrics = {}, {}
        for model, samples in cohorts.items():
            matrix = np.zeros((len(classes), len(classes)), dtype=int)
            for actual, predicted in samples.values():
                matrix[indices[actual], indices[predicted]] += 1
            matrices[model] = matrix
            per_class = {}
            for index, label in enumerate(classes):
                true_positive = int(matrix[index, index])
                support, predicted_count = int(matrix[index].sum()), int(matrix[:, index].sum())
                precision = None if predicted_count == 0 else true_positive / predicted_count
                recall = None if support == 0 else true_positive / support
                f1_denominator = support + predicted_count
                per_class[label] = {"support": support, "predicted_count": predicted_count,
                                    "precision": precision, "recall": recall,
                                    "f1": None if f1_denominator == 0 else 2 * true_positive / f1_denominator}
            metrics[model] = {"n": len(samples), "accuracy": float(np.trace(matrix) / len(samples)),
                              "classes": per_class, "counts": matrix.tolist()}
        stats.update({"classes": classes, "models": metrics, "same_cohort_verified": True,
                      "matrix_orientation": "rows observed; columns predicted; counts without normalization",
                      "zero_denominators": "undefined precision/recall/F1 recorded as null", "training_run_by_renderer": False})
        bundle = {"classes": classes, "matrices": matrices}
    bundle["statistics"] = stats
    _finite_statistics(stats)
    return bundle


def _axis(spec, role):
    return spec["axes"][role]["label"] + "\n(" + spec["axes"][role]["unit"] + ")"


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dfe5e8", linewidth=.5, alpha=.65, zorder=0)


def _density(values, grid):
    if np.ptp(values) == 0:
        return None
    std = float(np.std(values, ddof=1))
    iqr = float(np.percentile(values, 75) - np.percentile(values, 25))
    scale = min(std, iqr / 1.34) if iqr > 0 else std
    bandwidth = .9 * scale * len(values) ** (-.2)
    if not np.isfinite(bandwidth) or bandwidth <= 0:
        raise ValueError("Density bandwidth exceeds numeric range")
    with np.errstate(over="ignore", under="ignore"):
        z = (grid[:, None] - values[None, :]) / bandwidth
        result = np.exp(-.5 * z ** 2).mean(axis=1) / (bandwidth * np.sqrt(2 * np.pi))
    if not np.isfinite(result).all() or result.max() <= 0:
        raise ValueError("Density calculation exceeds numeric range")
    return result


def render_extension(spec, bundle, plt):
    """Render checked arrays. Fonts/title/provenance remain the caller's concern."""
    kind = spec["template_id"]
    if kind in NEW_EXTENSIONS:
        return _render_new(spec, bundle, plt)
    if kind == "residual-diagnostics":
        models = list(bundle["groups"])
        fig, axes = plt.subplots(len(models), 2, figsize=(6.3, 2.5 * len(models)), squeeze=False)
        unit = spec["axes"]["actual"]["unit"]
        for row, model in enumerate(models):
            left, right = axes[row]
            all_residuals = []
            for color, (split, values) in zip(COLORS, bundle["groups"][model].items()):
                residual = values[:, 1] - values[:, 0]
                left.scatter(values[:, 1], residual, s=13, color=color, alpha=.7, linewidths=0, label=split)
                all_residuals.append((split, residual, color))
            pooled = np.concatenate([residual for split, residual, color in all_residuals])
            edges = np.histogram_bin_edges(pooled, bins=min(15, max(1, int(np.sqrt(len(pooled))))))
            for split, residual, color in all_residuals:
                right.hist(residual, bins=edges, color=color, alpha=.3, edgecolor=color, linewidth=.6, label=split)
            left.axhline(0, color="#8998a5", linewidth=.9, linestyle="--")
            right.axvline(0, color="#8998a5", linewidth=.9, linestyle="--")
            left.set(xlabel=_axis(spec, "predicted"), ylabel=f"Predicted - observed ({unit})", title=model)
            right.set(xlabel=f"Residual ({unit})", ylabel="Observations", title="Residual distribution")
            left.legend(frameon=False, fontsize=6)
            for ax in (left, right):
                _style(ax)
        fig.subplots_adjust(left=.12, right=.98, bottom=.14, top=.84, hspace=.65, wspace=.35)
        return fig
    if kind == "confusion-matrix":
        models = list(bundle["matrices"])
        columns = min(2, len(models))
        rows = int(np.ceil(len(models) / columns))
        fig, axes = plt.subplots(rows, columns, figsize=(6.3, 3.4 * rows), squeeze=False)
        maximum = max(int(matrix.max()) for matrix in bundle["matrices"].values())
        for index, model in enumerate(models):
            ax = axes.flat[index]
            matrix = bundle["matrices"][model]
            artist = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=maximum)
            ax.set(xticks=range(len(bundle["classes"])), yticks=range(len(bundle["classes"])),
                   xticklabels=bundle["classes"], yticklabels=bundle["classes"],
                   xlabel="Predicted class", ylabel="Observed class", title=model)
            ax.tick_params(axis="x", rotation=35)
            if len(bundle["classes"]) <= 8:
                for r, c in np.ndindex(matrix.shape):
                    ax.text(c, r, str(matrix[r, c]), ha="center", va="center", fontsize=7,
                            color="white" if matrix[r, c] > maximum * .55 else "#243746")
            fig.colorbar(artist, ax=ax, shrink=.8, label="Observations")
        for index in range(len(models), rows * columns):
            axes.flat[index].set_visible(False)
        fig.subplots_adjust(left=.13, right=.97, bottom=.17, top=.83, wspace=.35, hspace=.6)
        return fig
    fig, ax = plt.subplots(figsize=(6.3, 4.4))
    _style(ax)
    note = None
    if kind in {"grouped-line", "uncertainty-band", "optimization-convergence"}:
        for color, (group, values) in zip(COLORS, bundle["groups"].items()):
            ax.plot(values[:, 0], values[:, 1], color=color, linewidth=1.4, marker="o", markersize=3, label=group)
            if kind == "uncertainty-band":
                ax.fill_between(values[:, 0], values[:, 2], values[:, 3], color=color, alpha=.18, linewidth=0)
        x, y = ("iteration", "objective") if kind == "optimization-convergence" else ("x", "estimate" if kind == "uncertainty-band" else "y")
        ax.set(xlabel=_axis(spec, x), ylabel=_axis(spec, y))
        note = spec["interval_note"] if kind == "uncertainty-band" else None
    elif kind in {"grouped-scatter", "pareto-front"}:
        for color, (group, values) in zip(COLORS, bundle["groups"].items()):
            ax.scatter(values[:, 0], values[:, 1], color=color, s=22, alpha=.72, linewidths=0, label=group)
        if kind == "pareto-front":
            front = bundle["front"]
            ax.scatter(front[:, 0], front[:, 1], s=64, facecolors="none", edgecolors="#243746", linewidths=1.2,
                       label="Nondominated supplied candidates")
            note = f"Objectives: x {spec['x_direction']}, y {spec['y_direction']}. Supplied candidates only."
        ax.set(xlabel=_axis(spec, "x"), ylabel=_axis(spec, "y"))
    elif kind in {"grouped-box", "grouped-violin"}:
        names = list(bundle["groups"])
        for index, (color, (group, values)) in enumerate(zip(COLORS, bundle["groups"].items())):
            if kind == "grouped-box":
                ax.boxplot([values], positions=[index], widths=.46, patch_artist=True,
                           boxprops={"facecolor": color, "edgecolor": color, "alpha": .25},
                           medianprops={"color": "#243746"}, whiskerprops={"color": color}, capprops={"color": color},
                           flierprops={"marker": "o", "markersize": 3, "markeredgecolor": color})
            else:
                pad = .1 * float(np.ptp(values)) if np.ptp(values) else max(abs(float(values[0])) * .05, 1)
                grid = np.linspace(values.min() - pad, values.max() + pad, 180)
                density = _density(values, grid)
                if density is not None:
                    width = .34 * density / density.max()
                    ax.fill_betweenx(grid, index - width, index + width, color=color, alpha=.3, linewidth=.6, edgecolor=color)
                ax.plot([index - .11, index + .11], [np.median(values)] * 2, color="#243746", linewidth=1.2)
            # Stable display offsets are derived from IDs, never numerical data.
            offsets = np.array([int(hashlib.sha256(sample.encode()).hexdigest()[:8], 16) / 0xffffffff
                                for sample in bundle["sample_ids"][group]]) * .12 - .06
            ax.scatter(index + offsets, values, color=color, s=8, alpha=.5, linewidths=0, zorder=3)
        ax.set(xticks=range(len(names)), xticklabels=names, ylabel=f"Value ({spec['unit']})")
        ax.tick_params(axis="x", rotation=20 if any(len(name) > 12 for name in names) else 0)
    elif kind == "distribution-histogram":
        for color, (group, values) in zip(COLORS, bundle["groups"].items()):
            ax.hist(values, bins=bundle["edges"], color=color, alpha=.3, edgecolor=color, linewidth=.8, label=group)
        ax.set(xlabel=f"Value ({spec['unit']})", ylabel="Observations")
    elif kind == "ecdf-distribution":
        for color, (group, curve) in zip(COLORS, bundle["curves"].items()):
            x, y = curve["value"], curve["probability"]
            ax.step([x[0]] + x, [0.] + y, where="post", color=color, linewidth=1.5, label=group)
            ax.scatter(x, y, color=color, s=9, linewidths=0)
        ax.set(xlabel=f"Value ({spec['unit']})", ylabel="Empirical cumulative probability", ylim=(0, 1.03))
    elif kind in {"grouped-bar", "stacked-bar"}:
        indices = np.arange(len(bundle["rows"]))
        width = .76 / len(bundle["columns"])
        bottom = np.zeros(len(indices))
        for index, (color, series) in enumerate(zip(COLORS, bundle["columns"])):
            values = bundle["matrix"][:, index]
            if kind == "stacked-bar":
                ax.bar(indices, values, bottom=bottom, width=.72, color=color, label=series, zorder=2)
                bottom += values
            else:
                offset = (index - (len(bundle["columns"]) - 1) / 2) * width
                ax.bar(indices + offset, values, width=width * .9, color=color, label=series, zorder=2)
        ax.set(xticks=indices, xticklabels=bundle["rows"], ylabel=f"Value ({spec['unit']})")
        ax.tick_params(axis="x", rotation=25)
    elif kind == "matrix-heatmap":
        matrix = bundle["matrix"]
        diverging = matrix.min() < 0 < matrix.max()
        limit = float(np.abs(matrix).max())
        artist = ax.imshow(matrix, cmap="RdBu_r" if diverging else "Blues", aspect="auto",
                           vmin=-limit if diverging else float(matrix.min()), vmax=limit if diverging else float(matrix.max()))
        ax.grid(False)
        ax.set(xticks=range(len(bundle["columns"])), xticklabels=bundle["columns"],
               yticks=range(len(bundle["rows"])), yticklabels=bundle["rows"])
        ax.tick_params(axis="x", rotation=35)
        if max(matrix.shape) <= 8:
            norm = artist.norm(matrix)
            for r, c in np.ndindex(matrix.shape):
                dark = norm[r, c] > .65 if not diverging else abs(norm[r, c] - .5) > .32
                ax.text(c, r, f"{matrix[r, c]:.3g}", ha="center", va="center", fontsize=7,
                        color="white" if dark else "#243746")
        fig.colorbar(artist, ax=ax, shrink=.85, label=f"Value ({spec['unit']})")
    elif kind == "binary-pr-comparison":
        for color, (model, curve) in zip(COLORS, bundle["curves"].items()):
            ax.step(curve["recall"], curve["precision"], where="pre", color=color, linewidth=1.6,
                    label=f"{model}: AP={curve['average_precision']:.3f}")
        prevalence = next(iter(bundle["curves"].values()))["prevalence"]
        ax.axhline(prevalence, color="#8998a5", linestyle="--", linewidth=.8, label=f"Cohort prevalence ({prevalence:.3f})")
        ax.set(xlim=(0, 1), ylim=(0, 1.04), xlabel="Recall", ylabel="Precision")
        note = "Supplied scores; equal-score ties move together. AP uses recall-increment weighting."
    else:
        raise ValueError("Unknown scientific chart extension")
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(frameon=False, fontsize=7, loc="best")
    if note:
        fig.text(.5, .025, note, ha="center", fontsize=6.5, wrap=True)
    fig.subplots_adjust(left=.13, right=.96, bottom=.22 if note else .18, top=.85)
    return fig


def _option_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite numeric JSON value")
    return float(value)


def _identified_points(rows, roles, values):
    ids, points, seen = [], [], set()
    for line, row in enumerate(rows, 2):
        sample = _text(row, roles["sample_id"], line)
        if sample in seen:
            raise ValueError("Duplicate sample ID; aggregate repeated measurements explicitly")
        ids.append(sample)
        seen.add(sample)
        points.append([_number(row, roles[role], line) for role in values])
    return ids, np.asarray(points, dtype=float)


def _rectangular_matrix(rows, roles):
    names, columns, cells = [], [], {}
    for line, row in enumerate(rows, 2):
        first = _text(row, roles["row"], line)
        second = _text(row, roles["column"], line)
        if (first, second) in cells:
            raise ValueError("Duplicate matrix/profile cell; aggregate explicitly")
        cells[first, second] = _number(row, roles["value"], line)
        if first not in names:
            names.append(first)
        if second not in columns:
            columns.append(second)
    if len(cells) != len(names) * len(columns):
        raise ValueError("A complete matrix/profile table is required; missing cells are not zero")
    return names, columns, np.asarray([[cells[a, b] for b in columns] for a in names])


def _prepare_new(spec, rows, roles, stats):
    kind = spec["template_id"]
    if kind in {"hexbin-density", "density-contour", "spatial-point-values"}:
        numeric_roles = ("x", "y", "value") if kind == "spatial-point-values" else ("x", "y")
        ids, values = _identified_points(rows, roles, numeric_roles)
        stats.update({"sample_ids": ids, "x_summary": _summary(values[:, 0]), "y_summary": _summary(values[:, 1])})
        bundle = {"values": values}
        if kind in {"hexbin-density", "density-contour"}:
            if len(values) < 3 or any(np.ptp(values[:, index]) <= 0 for index in (0, 1)):
                raise ValueError("Binned density needs at least three points with variation on both axes")
            if not np.isfinite(np.ptp(values, axis=0)).all():
                raise ValueError("Density coordinate range exceeds finite numeric range")
        if kind == "hexbin-density":
            gridsize = spec.get("gridsize", 24)
            if type(gridsize) is not int or not 4 <= gridsize <= 80:
                raise ValueError("gridsize must be an integer from 4 to 80")
            bundle["gridsize"] = gridsize
            stats.update({"gridsize": gridsize, "density_meaning": "observations per hexagonal bin, not probability density",
                          "bin_receipt": "computed from the actual Matplotlib collection during rendering"})
        elif kind == "density-contour":
            if spec["density_method"] != "histogram":
                raise ValueError("density_method must be histogram; this adapter does not estimate KDE")
            bins = spec.get("bins", 16)
            if type(bins) is not int or not 4 <= bins <= 60:
                raise ValueError("bins must be an integer from 4 to 60")
            counts, xedges, yedges = np.histogram2d(values[:, 0], values[:, 1], bins=bins)
            areas = np.diff(xedges)[:, None] * np.diff(yedges)[None, :]
            if not np.isfinite(areas).all() or (areas <= 0).any():
                raise ValueError("Density bin area exceeds finite numeric range or resolution")
            density = counts / len(values) / areas
            stats.update({"density_method": "rectangular histogram; contour rendering between bin centers only",
                          "bins": bins, "x_edges": xedges.tolist(), "y_edges": yedges.tolist(),
                          "counts": counts.astype(int).tolist(), "density": density.tolist(),
                          "density_integral": float(np.sum(density * areas)),
                          "density_unit": f"1/({spec['axes']['x']['unit']}*{spec['axes']['y']['unit']})",
                          "kde_fit": False, "spatial_interpolation": False})
            bundle.update(counts=counts, density=density, xedges=xedges, yedges=yedges)
        else:
            coordinate_system = spec["coordinate_system"]
            if coordinate_system not in {"planar", "lonlat"}:
                raise ValueError("coordinate_system must be planar or lonlat")
            if len({tuple(item[:2]) for item in values}) != len(values):
                raise ValueError("Duplicate spatial coordinate; choose an explicit aggregation before plotting")
            xunit, yunit = (spec["axes"][axis]["unit"] for axis in ("x", "y"))
            if coordinate_system == "lonlat":
                if xunit != "degree" or yunit != "degree":
                    raise ValueError("lonlat coordinates require degree units: x longitude, y latitude")
                if (np.abs(values[:, 0]) > 180).any() or (np.abs(values[:, 1]) > 90).any():
                    raise ValueError("Longitude must be in [-180,180] and latitude in [-90,90]")
            elif xunit != yunit:
                raise ValueError("Planar x/y coordinates must use the same unit for equal physical scale")
            stats.update({"coordinate_system": coordinate_system, "value_summary": _summary(values[:, 2]),
                          "coordinates": values.tolist(), "map_projection": "none; native coordinate axes",
                          "basemap": False, "spatial_interpolation": False})
        return bundle
    if kind in {"coefficient-forest", "sensitivity-tornado"}:
        name_role = "term" if kind == "coefficient-forest" else "parameter"
        value_roles = ("estimate", "lower", "upper") if kind == "coefficient-forest" else ("baseline", "lower_case", "upper_case")
        names, records = [], []
        for line, row in enumerate(rows, 2):
            name = _text(row, roles[name_role], line)
            if name in names:
                raise ValueError("Duplicate coefficient term or sensitivity parameter")
            names.append(name)
            record = [_number(row, roles[role], line) for role in value_roles]
            if kind == "coefficient-forest" and not record[1] <= record[0] <= record[2]:
                raise ValueError("Supplied lower <= estimate <= upper is required")
            records.append(record)
        if len(names) > 25:
            raise ValueError("Select at most 25 terms/parameters; split dense figures")
        values = np.asarray(records)
        if kind == "coefficient-forest":
            reference = _option_number(spec.get("reference_value", 0), "reference_value")
            stats.update({"terms": names, "supplied_intervals": values.tolist(), "interval_note": spec["interval_note"],
                          "reference_value": reference, "regression_fit_by_renderer": False})
            return {"names": names, "values": values, "reference": reference}
        if (values[:, 0] != values[0, 0]).any():
            raise ValueError("Tornado scenarios require a common supplied baseline outcome")
        delta = values[:, 1:] - values[:, :1]
        stats.update({"parameters": names, "baseline": float(values[0, 0]), "scenario_outcomes": values[:, 1:].tolist(),
                      "outcome_differences": delta.tolist(), "scenario_note": spec["scenario_note"],
                      "parameter_scenarios_run_by_renderer": False,
                      "scope": "low/high denote the supplied parameter scenarios; output direction need not be monotone"})
        return {"names": names, "delta": delta, "baseline": float(values[0, 0])}
    if kind in {"multimetric-profile", "bubble-matrix"}:
        matrix_roles = dict(roles, row=roles.get("series"), column=roles.get("metric")) if kind == "multimetric-profile" else roles
        names, columns, values = _rectangular_matrix(rows, matrix_roles)
        if kind == "multimetric-profile":
            if not 1 <= len(names) <= 6 or not 3 <= len(columns) <= 12:
                raise ValueError("Profiles need one to six series and three to twelve metrics")
            minimum, maximum = (_option_number(spec[key], key) for key in ("scale_min", "scale_max"))
            if minimum >= maximum or (values < minimum).any() or (values > maximum).any():
                raise ValueError("Values must lie within explicit scale_min < scale_max")
            stats.update({"series": names, "metrics": columns, "values": values.tolist(), "scale_min": minimum,
                          "scale_max": maximum, "scale_note": spec["scale_note"], "normalization_performed": False,
                          "ranking_inferred": False})
        else:
            if len(names) > 18 or len(columns) > 18 or (values < 0).any():
                raise ValueError("Bubble matrices need at most 18x18 cells and nonnegative values")
            stats.update({"row_labels": names, "column_labels": columns, "matrix": values.tolist(),
                          "area_mapping": "circle area proportional to supplied nonnegative value; zeros marked with x",
                          "maximum_value": float(values.max()), "input_aggregation": "none"})
        return {"names": names, "columns": columns, "values": values}
    if kind in {"ridge-distribution", "qq-normal"}:
        groups = _identified_groups(rows, roles, ("value",))
        if any(len(group) < 2 for group in groups.values()):
            raise ValueError("Each distribution group needs at least two identified observations")
        values = {name: np.asarray([item[1] for item in group]) for name, group in groups.items()}
        stats["groups"] = {name: _summary(items) for name, items in values.items()}
        if kind == "ridge-distribution":
            pooled = np.concatenate(list(values.values()))
            span = np.ptp(pooled)
            pad = .12 * span if span else max(abs(float(pooled[0])) * .05, 1)
            grid = np.linspace(pooled.min() - pad, pooled.max() + pad, 240)
            if not np.isfinite(grid).all():
                raise ValueError("Density grid exceeds finite numeric range")
            densities = {name: _density(items, grid) for name, items in values.items()}
            stats.update({"kde": "Gaussian KDE with Silverman bandwidth; constants omit KDE",
                          "grid": grid.tolist(), "density_by_group": {name: None if density is None else density.tolist() for name, density in densities.items()},
                          "constant_groups": [name for name, density in densities.items() if density is None],
                          "display_scale": "common density-to-height multiplier; curve values are not normalized per group"})
            return {"groups": values, "grid": grid, "densities": densities}
        quantiles = {}
        for name, items in values.items():
            probabilities = (np.arange(len(items)) + .5) / len(items)
            theoretical = np.asarray([NormalDist().inv_cdf(float(p)) for p in probabilities])
            quantiles[name] = {"probabilities": probabilities.tolist(), "standard_normal": theoretical.tolist(),
                               "observed": np.sort(items).tolist(), "reference_mean": float(items.mean()),
                               "reference_sd": float(items.std(ddof=1))}
        stats.update({"quantiles": quantiles, "plotting_position": "(i - 0.5)/n, i=1..n",
                      "reference_line": "sample mean + sample standard deviation * standard-normal quantile",
                      "normality_test_performed": False, "normality_assumed": False})
        return {"quantiles": quantiles}
    # Empirical calibration is a descriptive check of supplied probabilities.
    edges_raw = spec["bin_edges"]
    if not isinstance(edges_raw, list) or not 3 <= len(edges_raw) <= 31:
        raise ValueError("bin_edges must contain three to thirty-one explicit probability boundaries")
    edges = np.asarray([_option_number(value, "bin edge") for value in edges_raw])
    if edges[0] != 0 or edges[-1] != 1 or (np.diff(edges) <= 0).any():
        raise ValueError("bin_edges must strictly increase from 0 to 1")
    cohorts = {}
    for line, row in enumerate(rows, 2):
        model, sample = (_text(row, roles[role], line) for role in ("model", "sample_id"))
        label, score = (_number(row, roles[role], line) for role in ("label", "score"))
        if label not in {0, 1} or not 0 <= score <= 1:
            raise ValueError("Calibration needs binary 0/1 labels and probabilities in [0,1]")
        if sample in cohorts.setdefault(model, {}):
            raise ValueError("Duplicate model/sample ID")
        cohorts[model][sample] = (label, score)
    _limit(cohorts, 6)
    reference = next(iter(cohorts.values()))
    if {pair[0] for pair in reference.values()} != {0, 1}:
        raise ValueError("Calibration comparison requires both observed classes")
    models = {}
    for model, samples in cohorts.items():
        if samples.keys() != reference.keys() or any(pair[0] != reference[sample][0] for sample, pair in samples.items()):
            raise ValueError("Calibration models require the same sample cohort and actual labels")
        values = np.asarray(list(samples.values()))
        assignments = np.minimum(np.searchsorted(edges, values[:, 1], side="right") - 1, len(edges) - 2)
        bins = []
        for index in range(len(edges) - 1):
            members = values[assignments == index]
            bins.append({"lower": float(edges[index]), "upper": float(edges[index + 1]), "n": len(members),
                         "mean_probability": None if not len(members) else float(members[:, 1].mean()),
                         "observed_fraction": None if not len(members) else float(members[:, 0].mean())})
        brier = float(np.mean((values[:, 1] - values[:, 0]) ** 2))
        ece = float(sum(item["n"] / len(values) * abs(item["mean_probability"] - item["observed_fraction"]) for item in bins if item["n"]))
        models[model] = {"n": len(values), "bins": bins, "brier_score": brier, "ece_for_declared_bins": ece}
    stats.update({"models": models, "bin_edges": edges.tolist(), "same_cohort_verified": True,
                  "bin_definition": "[lower, upper), except final bin includes probability 1; empty bins remain null",
                  "calibration_fit_by_renderer": False, "uncertainty_estimated": False,
                  "scope": "descriptive calibration and Brier/ECE of supplied probabilities; no independent-validation claim"})
    return {"models": models}


def _render_new(spec, bundle, plt):
    kind = spec["template_id"]
    if kind == "qq-normal":
        count = len(bundle["quantiles"])
        columns = min(2, count)
        rows = int(np.ceil(count / columns))
        fig = plt.figure(figsize=(6.3, 2.8 * rows))
        grid = fig.add_gridspec(rows, columns)
        axes = [fig.add_subplot(grid[index // columns, :] if index == count - 1 and count % columns else grid[index // columns, index % columns])
                for index in range(count)]
        for ax, (name, curve), color in zip(axes, bundle["quantiles"].items(), COLORS):
            x, y = np.asarray(curve["standard_normal"]), np.asarray(curve["observed"])
            ax.scatter(x, y, color=color, s=14, linewidths=0)
            ax.plot(x, curve["reference_mean"] + curve["reference_sd"] * x, linestyle="--", color="#8998a5", linewidth=.9)
            ax.set(xlabel="Standard-normal theoretical quantile", ylabel=f"Ordered value ({spec['unit']})", title=name)
            _style(ax)
        fig.subplots_adjust(left=.12, right=.97, bottom=.14, top=.84, wspace=.4, hspace=.7)
        return fig
    if kind == "multimetric-profile":
        fig, ax = plt.subplots(figsize=(6.3, 5.2), subplot_kw={"projection": "polar"})
        angles = np.linspace(0, 2 * np.pi, len(bundle["columns"]), endpoint=False)
        closed_angles = np.r_[angles, angles[0]]
        for color, name, values in zip(COLORS, bundle["names"], bundle["values"]):
            ax.plot(closed_angles, np.r_[values, values[0]], color=color, linewidth=1.4, marker="o", markersize=3, label=name)
        ax.set(xticks=angles, xticklabels=bundle["columns"], ylim=(spec["scale_min"], spec["scale_max"]))
        ax.tick_params(pad=8)
        ax.legend(loc="upper left", bbox_to_anchor=(1.03, 1), frameon=False, fontsize=7)
        fig.text(.5, .035, spec["scale_note"] + f" ({spec['unit']})", ha="center", fontsize=6.5, wrap=True)
        fig.subplots_adjust(left=.1, right=.78, bottom=.13, top=.82)
        return fig
    height = max(4.5, 1.8 + .23 * len(bundle["names"])) if kind in {"coefficient-forest", "sensitivity-tornado"} else 4.5
    fig, ax = plt.subplots(figsize=(6.3, height))
    _style(ax)
    note = None
    if kind == "hexbin-density":
        values = bundle["values"]
        artist = ax.hexbin(values[:, 0], values[:, 1], gridsize=bundle["gridsize"], mincnt=1, cmap="Blues", linewidths=.15)
        counts, centers = np.asarray(artist.get_array()), artist.get_offsets()
        if int(counts.sum()) != len(values):
            raise ValueError("Rendered hexbin count does not conserve supplied observations")
        bundle["statistics"]["rendered_hexagons"] = {"centers": centers.tolist(), "counts": counts.astype(int).tolist(), "total": int(counts.sum())}
        fig.colorbar(artist, ax=ax, label="Observations per hexagonal bin")
        ax.set(xlabel=_axis(spec, "x"), ylabel=_axis(spec, "y"))
    elif kind == "density-contour":
        x = bundle["xedges"][:-1] + np.diff(bundle["xedges"]) / 2
        y = bundle["yedges"][:-1] + np.diff(bundle["yedges"]) / 2
        artist = ax.contourf(x, y, bundle["density"].T, levels=8, cmap="Blues")
        ax.scatter(bundle["values"][:, 0], bundle["values"][:, 1], s=6, c="#243746", alpha=.35, linewidths=0)
        fig.colorbar(artist, ax=ax, label=bundle["statistics"]["density_unit"])
        ax.set(xlabel=_axis(spec, "x"), ylabel=_axis(spec, "y"))
    elif kind == "coefficient-forest":
        values, indices = bundle["values"], np.arange(len(bundle["names"]))
        ax.errorbar(values[:, 0], indices, xerr=np.array([values[:, 0] - values[:, 1], values[:, 2] - values[:, 0]]),
                    fmt="o", color=COLORS[0], capsize=3, markersize=4, linewidth=1.2)
        ax.axvline(bundle["reference"], linestyle="--", color="#8998a5", linewidth=.9)
        ax.set(yticks=indices, yticklabels=bundle["names"], xlabel=_axis(spec, "estimate"))
        ax.invert_yaxis()
        note = spec["interval_note"]
    elif kind == "sensitivity-tornado":
        delta = bundle["delta"]
        order = np.argsort(-np.abs(delta).max(axis=1), kind="mergesort")
        y = np.arange(len(order))
        ax.barh(y - .16, delta[order, 0], height=.3, color=COLORS[0], label="Low parameter scenario")
        ax.barh(y + .16, delta[order, 1], height=.3, color=COLORS[1], label="High parameter scenario")
        ax.axvline(0, color="#8998a5", linewidth=.9)
        ax.set(yticks=y, yticklabels=[bundle["names"][index] for index in order],
               xlabel=spec["axes"]["baseline"]["label"] + f" - baseline ({bundle['baseline']:.4g})\n(" + spec["axes"]["baseline"]["unit"] + ")")
        ax.invert_yaxis()
        note = spec["scenario_note"]
    elif kind == "bubble-matrix":
        values = bundle["values"]
        y, x = np.indices(values.shape)
        maximum = float(values.max())
        area = np.zeros_like(values) if maximum == 0 else 650 * values / maximum
        artist = ax.scatter(x.ravel(), y.ravel(), s=area.ravel(), c=values.ravel(), cmap="Blues", edgecolors="#527c7c", linewidths=.5)
        zeros = values == 0
        ax.scatter(x[zeros], y[zeros], s=14, marker="x", c="#8998a5", linewidths=.7)
        ax.set(xticks=range(len(bundle["columns"])), xticklabels=bundle["columns"], yticks=range(len(bundle["names"])),
               yticklabels=bundle["names"], xlim=(-.65, len(bundle["columns"]) - .35), ylim=(len(bundle["names"]) - .35, -.65))
        ax.tick_params(axis="x", rotation=30)
        fig.colorbar(artist, ax=ax, label=f"Supplied value ({spec['unit']})")
        if maximum > 0:
            for fraction in (.25, .5, 1):
                ax.scatter([], [], s=650 * fraction, edgecolor="#527c7c", facecolor="none", label=f"{maximum * fraction:.3g}")
            ax.legend(title=f"Circle area ({spec['unit']})", loc="upper left", bbox_to_anchor=(1.15, 1),
                      frameon=False, labelspacing=2.5, handleheight=3, handlelength=5, handletextpad=2, fontsize=7)
        note = "Circle area proportional to value; x = 0."
    elif kind == "ridge-distribution":
        maximum = max((density.max() for density in bundle["densities"].values() if density is not None), default=1.)
        for index, (color, (name, values)) in enumerate(zip(COLORS, bundle["groups"].items())):
            density = bundle["densities"][name]
            ax.axhline(index, color="#dfe5e8", linewidth=.6)
            if density is not None:
                height = .78 * density / maximum
                ax.fill_between(bundle["grid"], index, index + height, color=color, alpha=.4)
                ax.plot(bundle["grid"], index + height, color=color, linewidth=1)
            ax.plot(values, np.full(len(values), index - .07), "|", color=color, markersize=5, alpha=.6)
            if density is None:
                ax.annotate("constant; KDE omitted", (values[0], index + .1), fontsize=6.5)
        ax.set(yticks=range(len(bundle["groups"])), yticklabels=list(bundle["groups"]), xlabel=f"Value ({spec['unit']})")
        note = "Gaussian KDE; shared density scale; ticks represent observations."
    elif kind == "calibration-curve":
        ax.plot([0, 1], [0, 1], linestyle="--", color="#8998a5", linewidth=.9, label="Identity")
        for color, (model, data) in zip(COLORS, bundle["models"].items()):
            populated = [item for item in data["bins"] if item["n"]]
            ax.plot([item["mean_probability"] for item in populated], [item["observed_fraction"] for item in populated],
                    color=color, marker="o", linewidth=1.3, markersize=4, label=f"{model}: Brier={data['brier_score']:.3g}")
        ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Mean supplied probability in bin", ylabel="Observed positive fraction in bin")
        note = "Bins: [lower, upper); final bin includes 1."
    else:  # spatial-point-values
        values = bundle["values"]
        artist = ax.scatter(values[:, 0], values[:, 1], c=values[:, 2], cmap="viridis", s=35, edgecolors="white", linewidths=.4)
        fig.colorbar(artist, ax=ax, label=_axis(spec, "value"))
        ax.set(xlabel=_axis(spec, "x"), ylabel=_axis(spec, "y"))
        if spec["coordinate_system"] == "planar":
            ax.set_aspect("equal", adjustable="box")
    handles, _ = ax.get_legend_handles_labels()
    if handles and kind != "bubble-matrix":
        ax.legend(frameon=False, fontsize=7, loc="best")
    if note:
        fig.text(.5, .02, note, ha="center", fontsize=6.5, wrap=True)
    fig.subplots_adjust(left=.2 if kind in {"coefficient-forest", "sensitivity-tornado"} else .13,
                        right=.8 if kind == "bubble-matrix" else .94, bottom=.23 if note else .18, top=.84)
    # Matplotlib rasterizes dense colorbar solids by default. These figures are
    # native supplied-data geometry; keep colorbars as vectors as well.
    for figure_axis in fig.axes:
        for collection in figure_axis.collections:
            collection.set_rasterized(False)
    _finite_statistics(bundle["statistics"])
    return fig
