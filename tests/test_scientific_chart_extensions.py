"""Independent numerical checks and fail-closed CSV contract tests.

Fixtures are small synthetic software-test observations, never contest results.
"""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
import warnings

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scientific_chart_extensions", ROOT / "scripts/scientific_chart_extensions.py")
CHARTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHARTS)
HAS_MPL = importlib.util.find_spec("matplotlib") is not None


def contract(kind, **extras):
    meta = CHARTS.EXTENSIONS[kind]
    spec = {"schema_version": 1, "template_id": kind, "data_kind": "synthetic",
            "data": "test-fixture.csv", "title": "Synthetic software-test fixture",
            "roles": {role: role for role in meta["roles"]}}
    if meta["axes"]:
        spec["axes"] = {role: {"label": role, "unit": "1"} for role in meta["axes"]}
    if meta["unit"]:
        spec["unit"] = "1"
    spec.update(extras)
    return spec


def observations(kind):
    if kind in {"grouped-line", "uncertainty-band"}:
        result = [{"group": group, "x": str(x), "y": str(x + offset),
                   "estimate": str(x + offset), "lower": str(x + offset - .5), "upper": str(x + offset + .8)}
                  for group, offset in (("A", 0), ("B", 1)) for x in (3, 1, 2)]
    elif kind == "optimization-convergence":
        result = [{"group": group, "iteration": str(index), "objective": str(value)}
                  for group in ("A", "B") for index, value in enumerate((4, 2, 3))]
    elif kind in {"grouped-scatter", "pareto-front"}:
        result = [{"group": "A", "sample_id": sample_id, "x": str(x), "y": str(y)}
                  for sample_id, x, y in (("a", 1, 3), ("b", 2, 2), ("c", 3, 1), ("d", 3, 3), ("e", 1, 3))]
    elif kind in {"grouped-box", "grouped-violin", "distribution-histogram", "ecdf-distribution"}:
        result = [{"group": group, "sample_id": f"{group}{index}", "value": str(value)}
                  for group, values in (("A", (1, 1, 2, 4)), ("B", (2, 3, 4, 5)))
                  for index, value in enumerate(values)]
    elif kind in {"grouped-bar", "stacked-bar", "matrix-heatmap"}:
        result = [{"category": a, "series": b, "row": a, "column": b, "value": str(value)}
                  for a, b, value in (("A", "I", 2), ("A", "II", 3), ("B", "I", 4), ("B", "II", 1))]
    elif kind == "residual-diagnostics":
        result = [{"model": model, "split": "test", "sample_id": str(index), "actual": str(a), "predicted": str(p)}
                  for model in ("A", "B") for index, (a, p) in enumerate(((1, 2), (2, 2), (3, 2)))]
    elif kind == "binary-pr-comparison":
        result = [{"model": model, "sample_id": str(index), "label": str(label), "score": str(score)}
                  for model in ("A", "B") for index, (label, score) in enumerate(((1, .9), (0, .8), (1, .7), (0, .1)))]
    else:
        result = [{"model": model, "sample_id": str(index), "actual": actual, "predicted": predicted}
                  for model in ("A", "B") for index, (actual, predicted) in enumerate((("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")))]
    # A CSV normally can contain extra fields; only contracted roles are selected.
    return result


def fixture(kind):
    extras = ({"interval_note": "Supplied scenario envelope, not a confidence interval"} if kind == "uncertainty-band" else
              {"x_direction": "min", "y_direction": "min"} if kind == "pareto-front" else {})
    return contract(kind, **extras), observations(kind)


class ScientificChartExtensionChecks(unittest.TestCase):
    def test_exact_catalog_of_fifteen_adapters(self):
        self.assertEqual(len(CHARTS.EXTENSIONS), 15)
        for kind in CHARTS.EXTENSIONS:
            spec, rows = fixture(kind)
            bundle = CHARTS.prepare_extension(spec, rows)
            self.assertEqual(bundle["statistics"]["observations"], len(rows))
            self.assertFalse(bundle["statistics"]["confidence_interval_calculated"])
            self.assertFalse(bundle["statistics"]["missing_values_imputed"])
            json.dumps(bundle["statistics"], allow_nan=False)

    def test_every_role_must_exist_and_roles_cannot_alias(self):
        for kind in CHARTS.EXTENSIONS:
            with self.subTest(kind=kind):
                spec, rows = fixture(kind)
                del rows[0][CHARTS.EXTENSIONS[kind]["roles"][0]]
                with self.assertRaisesRegex(ValueError, "column"):
                    CHARTS.prepare_extension(spec, rows)
                spec, rows = fixture(kind)
                first, second = CHARTS.EXTENSIONS[kind]["roles"][:2]
                spec["roles"][second] = spec["roles"][first]
                with self.assertRaisesRegex(ValueError, "distinct"):
                    CHARTS.prepare_extension(spec, rows)

    def test_numeric_roles_reject_infinite_nan_and_missing_values(self):
        numeric_roles = {
            "grouped-line": "y", "uncertainty-band": "lower", "grouped-scatter": "x",
            "grouped-box": "value", "grouped-violin": "value", "distribution-histogram": "value",
            "ecdf-distribution": "value", "grouped-bar": "value", "stacked-bar": "value",
            "matrix-heatmap": "value", "residual-diagnostics": "predicted",
            "binary-pr-comparison": "score", "optimization-convergence": "objective", "pareto-front": "x"}
        for kind, role in numeric_roles.items():
            for value in ("inf", "NaN", "", None):
                with self.subTest(kind=kind, value=value):
                    spec, rows = fixture(kind)
                    rows[0][role] = value
                    with self.assertRaises(ValueError):
                        CHARTS.prepare_extension(spec, rows)

    def test_axes_units_unknown_fields_and_unproven_analysis_rejected(self):
        spec, rows = fixture("grouped-line")
        spec["axes"]["y"].pop("unit")
        with self.assertRaisesRegex(ValueError, "unit"):
            CHARTS.prepare_extension(spec, rows)
        for kind in CHARTS.EXTENSIONS:
            spec, rows = fixture(kind)
            spec["add_significance_stars"] = True
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                CHARTS.prepare_extension(spec, rows)
        spec, rows = fixture("grouped-box")
        spec["unit"] = ""
        with self.assertRaisesRegex(ValueError, "unit"):
            CHARTS.prepare_extension(spec, rows)

    def test_malformed_contract_types_are_reported_as_validation_errors(self):
        for field, value in (("template_id", []), ("data_kind", {}), ("roles", []),
                             ("axes", []), ("schema_version", True), ("title", None)):
            spec, rows = fixture("grouped-line")
            spec[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, rows)
        spec, rows = fixture("grouped-line")
        for wrong in (None, "not CSV records", [None], [{None: [1, 2]}]):
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, wrong)

    def test_line_orders_supplied_x_and_rejects_duplicate_coordinates(self):
        spec, rows = fixture("grouped-line")
        bundle = CHARTS.prepare_extension(spec, rows)
        np.testing.assert_array_equal(bundle["groups"]["A"], [[1, 1], [2, 2], [3, 3]])
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            CHARTS.prepare_extension(spec, rows)

    def test_line_cannot_imply_a_trend_from_one_point(self):
        spec, rows = fixture("grouped-line")
        with self.assertRaisesRegex(ValueError, "at least two"):
            CHARTS.prepare_extension(spec, rows[:1])

    def test_interval_kind_required_and_limits_cannot_be_reversed_or_exclude_estimate(self):
        spec, rows = fixture("uncertainty-band")
        supplied = CHARTS.prepare_extension(spec, rows)
        self.assertEqual(supplied["statistics"]["interval_note"], spec["interval_note"])
        spec.pop("interval_note")
        with self.assertRaisesRegex(ValueError, "interval_note"):
            CHARTS.prepare_extension(spec, rows)
        for lower, upper in (("99", "1"), ("0", "1"), ("4", "5")):
            spec, rows = fixture("uncertainty-band")
            rows[0].update(lower=lower, upper=upper)
            with self.assertRaisesRegex(ValueError, "lower"):
                CHARTS.prepare_extension(spec, rows)

    def test_identified_groups_reject_duplicate_and_cross_group_samples(self):
        for kind in ("grouped-scatter", "grouped-box", "grouped-violin", "distribution-histogram", "ecdf-distribution", "pareto-front"):
            spec, rows = fixture(kind)
            rows[-1]["sample_id"] = rows[0]["sample_id"]
            rows[-1]["group"] = "different"
            with self.assertRaisesRegex(ValueError, "sample ID"):
                CHARTS.prepare_extension(spec, rows)

    def test_distribution_summary_is_from_observations_and_histogram_conserves_counts(self):
        spec, rows = fixture("grouped-box")
        summary = CHARTS.prepare_extension(spec, rows)["statistics"]["groups"]["A"]
        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["mean"], 2)
        self.assertEqual(summary["median"], 1.5)
        self.assertEqual(summary["q1"], 1)
        self.assertEqual(summary["q3"], 2.5)
        self.assertAlmostEqual(summary["sd"], np.sqrt(2))
        spec, rows = fixture("distribution-histogram")
        spec["bins"] = 4
        histogram = CHARTS.prepare_extension(spec, rows)["statistics"]["histogram"]
        self.assertEqual(histogram["edges"], [1, 2, 3, 4, 5])
        self.assertEqual(histogram["group_counts"], {"A": [2, 1, 0, 1], "B": [0, 1, 1, 2]})
        for counts in histogram["group_counts"].values():
            self.assertEqual(sum(counts), 4)

    def test_histogram_bin_contract_is_explicit_integer(self):
        for bins in (True, 0, 61, 2.5, "4"):
            spec, rows = fixture("distribution-histogram")
            spec["bins"] = bins
            with self.assertRaisesRegex(ValueError, "bins"):
                CHARTS.prepare_extension(spec, rows)

    def test_ecdf_combines_ties_without_smoothing(self):
        spec, rows = fixture("ecdf-distribution")
        curve = CHARTS.prepare_extension(spec, rows)["statistics"]["ecdf"]["A"]
        self.assertEqual(curve, {"value": [1, 2, 4], "probability": [.5, .75, 1]})

    def test_constant_violin_has_no_fabricated_density(self):
        spec, rows = fixture("grouped-violin")
        for row in rows:
            if row["group"] == "A":
                row["value"] = "2"
        bundle = CHARTS.prepare_extension(spec, rows)
        self.assertEqual(bundle["statistics"]["constant_groups"], ["A"])
        self.assertIsNone(CHARTS._density(np.array([2., 2.]), np.array([1., 2., 3.])))

    def test_complete_matrices_preserve_input_cells_and_missing_cell_is_not_zero(self):
        for kind in ("grouped-bar", "stacked-bar", "matrix-heatmap"):
            spec, rows = fixture(kind)
            bundle = CHARTS.prepare_extension(spec, rows)
            np.testing.assert_array_equal(bundle["matrix"], [[2, 3], [4, 1]])
            if kind == "stacked-bar":
                self.assertEqual(bundle["statistics"]["category_totals"], {"A": 5, "B": 5})
            with self.assertRaisesRegex(ValueError, "complete"):
                CHARTS.prepare_extension(spec, rows[:-1])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                CHARTS.prepare_extension(spec, rows + [dict(rows[0])])

    def test_negative_stacked_components_rejected_but_signed_bar_and_heatmap_allowed(self):
        for kind in ("grouped-bar", "matrix-heatmap"):
            spec, rows = fixture(kind)
            rows[0]["value"] = "-2"
            self.assertEqual(CHARTS.prepare_extension(spec, rows)["matrix"][0, 0], -2)
        spec, rows = fixture("stacked-bar")
        rows[0]["value"] = "-2"
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            CHARTS.prepare_extension(spec, rows)

    def test_residuals_metrics_match_hand_calculation_and_require_common_units(self):
        spec, rows = fixture("residual-diagnostics")
        metric = CHARTS.prepare_extension(spec, rows)["statistics"]["metrics"]["A"]["test"]
        self.assertAlmostEqual(metric["rmse"], np.sqrt(2 / 3))
        self.assertAlmostEqual(metric["mae"], 2 / 3)
        self.assertEqual(metric["bias"], 0)
        self.assertEqual(metric["r2"], 0)
        self.assertEqual(metric["residual_summary"]["minimum"], -1)
        self.assertEqual(metric["residual_summary"]["maximum"], 1)
        spec["axes"]["predicted"]["unit"] = "kg"
        with self.assertRaisesRegex(ValueError, "same unit"):
            CHARTS.prepare_extension(spec, rows)

    def test_constant_observed_values_have_no_defined_r_squared(self):
        spec, rows = fixture("residual-diagnostics")
        for row in rows:
            row["actual"] = "2"
        metric = CHARTS.prepare_extension(spec, rows)["statistics"]["metrics"]["A"]["test"]
        self.assertIsNone(metric["r2"])
        self.assertEqual(metric["rmse"], 0)
        self.assertEqual(metric["bias"], 0)

    def test_model_comparisons_require_identical_cohort_and_truth(self):
        for kind in ("residual-diagnostics", "binary-pr-comparison", "confusion-matrix"):
            for damage in ("sample_id", "truth", "duplicate"):
                with self.subTest(kind=kind, damage=damage):
                    spec, rows = fixture(kind)
                    if damage == "sample_id":
                        rows[-1]["sample_id"] = "foreign-cohort"
                    elif damage == "truth":
                        role = "label" if kind == "binary-pr-comparison" else "actual"
                        rows[-1][role] = "0" if kind == "binary-pr-comparison" else "999"
                        if kind == "binary-pr-comparison":
                            rows[-1][role] = "1"  # last supplied label is 0
                    else:
                        rows.append(dict(rows[-1]))
                    with self.assertRaises(ValueError):
                        CHARTS.prepare_extension(spec, rows)

    def test_same_sample_cannot_leak_into_multiple_splits(self):
        spec, rows = fixture("residual-diagnostics")
        extra = dict(rows[0], split="training")
        with self.assertRaisesRegex(ValueError, "multiple splits"):
            CHARTS.prepare_extension(spec, rows + [extra])

    def test_pr_average_precision_is_not_trapezoid_area(self):
        curve = CHARTS.empirical_pr([1, 0, 1, 0], [.9, .8, .7, .1])
        self.assertEqual(curve["recall"], [0, .5, .5, 1, 1])
        self.assertEqual(curve["precision"], [1, 1, .5, 2 / 3, .5])
        self.assertAlmostEqual(curve["average_precision"], 5 / 6)
        trapezoid = sum((b - a) * (p + q) / 2 for a, b, p, q in zip(
            curve["recall"], curve["recall"][1:], curve["precision"], curve["precision"][1:]))
        self.assertNotAlmostEqual(curve["average_precision"], trapezoid)

    def test_pr_ties_move_together_and_permutation_does_not_change_ap(self):
        curve = CHARTS.empirical_pr([1, 0, 1, 0], [.5, .5, .5, .5])
        self.assertEqual(curve["thresholds"], [None, .5])
        self.assertEqual(curve["recall"], [0, 1])
        self.assertEqual(curve["precision"], [1, .5])
        self.assertEqual(curve["average_precision"], .5)
        a = CHARTS.empirical_pr([1, 0, 1, 0], [.9, .9, .5, .2])
        b = CHARTS.empirical_pr([0, 1, 0, 1], [.9, .9, .2, .5])
        self.assertEqual(a["average_precision"], b["average_precision"])
        self.assertEqual(a["recall"], b["recall"])

    def test_pr_invalid_labels_single_class_and_misalignment_rejected(self):
        for labels, scores in (([1, 2], [.4, .5]), ([1, 1], [.4, .5]), ([0, 0], [.4, .5]), ([0, 1], [.4]), ([], [])):
            with self.assertRaises(ValueError):
                CHARTS.empirical_pr(labels, scores)

    def test_confusion_matrix_counts_and_undefined_class_rates(self):
        spec, rows = fixture("confusion-matrix")
        spec["classes"] = ["A", "B", "absent"]
        bundle = CHARTS.prepare_extension(spec, rows)
        metric = bundle["statistics"]["models"]["A"]
        self.assertEqual(metric["counts"], [[1, 1, 0], [1, 1, 0], [0, 0, 0]])
        self.assertEqual(metric["accuracy"], .5)
        self.assertEqual(metric["classes"]["A"]["precision"], .5)
        self.assertEqual(metric["classes"]["B"]["recall"], .5)
        self.assertEqual(metric["classes"]["absent"], {"support": 0, "predicted_count": 0,
                                                       "precision": None, "recall": None, "f1": None})

    def test_confusion_class_contract_covers_observed_and_predicted_values(self):
        for classes in (["A", "A"], ["A", "absent"], ["A"], "A,B"):
            spec, rows = fixture("confusion-matrix")
            spec["classes"] = classes
            with self.assertRaisesRegex(ValueError, "classes"):
                CHARTS.prepare_extension(spec, rows)

    def test_optimization_supplied_nonmonotonic_values_not_replaced_by_best_so_far(self):
        spec, rows = fixture("optimization-convergence")
        bundle = CHARTS.prepare_extension(spec, rows)
        np.testing.assert_array_equal(bundle["groups"]["A"][:, 1], [4, 2, 3])
        self.assertFalse(bundle["statistics"]["optimizer_run_by_renderer"])
        for iteration in ("-.5", "-1", ".5"):
            damaged = copy.deepcopy(rows)
            damaged[0]["iteration"] = iteration
            with self.assertRaisesRegex(ValueError, "integer"):
                CHARTS.prepare_extension(spec, damaged)

    def test_pareto_honors_all_explicit_direction_pairs_and_preserves_duplicate_objectives(self):
        expected = {("min", "min"): {"a", "b", "c", "e"}, ("max", "max"): {"d"},
                    ("min", "max"): {"a", "e"}, ("max", "min"): {"c"}}
        for directions, ids in expected.items():
            spec, rows = fixture("pareto-front")
            spec.update(x_direction=directions[0], y_direction=directions[1])
            stats = CHARTS.prepare_extension(spec, rows)["statistics"]
            self.assertEqual(set(stats["nondominated_sample_ids"]), ids)
            self.assertEqual(stats["nondominated_count"], len(ids))
            self.assertFalse(stats["optimizer_run_by_renderer"])
        for invalid in (None, "ascending", ""):
            spec, rows = fixture("pareto-front")
            spec["x_direction"] = invalid
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, rows)

    def test_pareto_membership_matches_independent_pairwise_definition(self):
        # The production algorithm sorts objectives; the oracle checks each
        # candidate against every supplied candidate, including tied coordinates.
        rng = np.random.default_rng(73)
        values = rng.integers(-5, 6, size=(90, 2))
        rows = [{"group": "candidates", "sample_id": str(index), "x": str(x), "y": str(y)}
                for index, (x, y) in enumerate(values)]
        for x_direction in ("min", "max"):
            for y_direction in ("min", "max"):
                expected = set()
                for index, (x, y) in enumerate(values):
                    dominated = False
                    for other_x, other_y in values:
                        better_x = other_x <= x if x_direction == "min" else other_x >= x
                        better_y = other_y <= y if y_direction == "min" else other_y >= y
                        if better_x and better_y and (other_x != x or other_y != y):
                            dominated = True
                            break
                    if not dominated:
                        expected.add(str(index))
                spec = contract("pareto-front", x_direction=x_direction, y_direction=y_direction)
                stats = CHARTS.prepare_extension(spec, rows)["statistics"]
                self.assertEqual(set(stats["nondominated_sample_ids"]), expected)

    def test_aggregate_overflow_rejected_instead_of_writing_infinite_metrics(self):
        spec, rows = fixture("stacked-bar")
        for row in rows:
            row["value"] = "1e308"
        with self.assertRaisesRegex(ValueError, "finite numeric range"):
            CHARTS.prepare_extension(spec, rows)

    def test_categorical_whitespace_empty_labels_and_empty_rows_rejected(self):
        for label in ("", " A", None):
            spec, rows = fixture("grouped-line")
            rows[0]["group"] = label
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, rows)
        spec, rows = fixture("grouped-line")
        with self.assertRaisesRegex(ValueError, "no observations"):
            CHARTS.prepare_extension(spec, [])

    @unittest.skipUnless(HAS_MPL, "Matplotlib is optional on validation-only hosts")
    def test_all_fifteen_adapters_render_png_pdf_svg_without_missing_glyph_warnings(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for kind in CHARTS.EXTENSIONS:
            with self.subTest(kind=kind), warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                spec, rows = fixture(kind)
                bundle = CHARTS.prepare_extension(spec, rows)
                fig = CHARTS.render_extension(spec, bundle, plt)
                self.assertGreaterEqual(len(fig.axes), 1)
                for suffix in ("png", "pdf", "svg"):
                    stream = io.BytesIO()
                    fig.savefig(stream, format=suffix, dpi=55, facecolor="white")
                    self.assertGreater(len(stream.getvalue()), 500)
                plt.close(fig)
                self.assertFalse([str(item.message) for item in captured if "Glyph" in str(item.message)])


if __name__ == "__main__":
    unittest.main()
