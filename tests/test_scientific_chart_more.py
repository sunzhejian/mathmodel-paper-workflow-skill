"""Numerical and rejection checks for ten additional supplied-data figures."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import warnings

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("more_charts", ROOT / "scripts/scientific_chart_extensions.py")
CHARTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHARTS)
HAS_MPL = importlib.util.find_spec("matplotlib") is not None


def fixture(kind):
    meta = CHARTS.NEW_EXTENSIONS[kind]
    spec = dict(schema_version=1, template_id=kind, data_kind="synthetic", data="data.csv", title="Synthetic chart fixture",
                roles={role: role for role in meta["roles"]})
    if meta["axes"]:
        spec["axes"] = {role: {"label": role, "unit": "1"} for role in meta["axes"]}
    if meta["unit"]:
        spec["unit"] = "1"
    if kind in {"hexbin-density", "density-contour", "spatial-point-values"}:
        rows = [dict(sample_id=str(index), x=str(x), y=str(y), value=str(index + 2))
                for index, (x, y) in enumerate(((0, 0), (1, 1), (2, 2), (3, 3)))]
        if kind == "density-contour":
            spec.update(density_method="histogram", bins=4)
        if kind == "spatial-point-values":
            spec["coordinate_system"] = "planar"
    elif kind == "coefficient-forest":
        spec["interval_note"] = "Provided scenario interval, not estimated CI"
        rows = [dict(term=name, estimate=str(value), lower=str(value - .5), upper=str(value + .4))
                for name, value in (("A", .2), ("B", -.3))]
    elif kind == "sensitivity-tornado":
        spec["scenario_note"] = "Provided low/high parameter scenarios, no solver execution"
        rows = [dict(parameter="A", baseline="100", lower_case="110", upper_case="90"),
                dict(parameter="B", baseline="100", lower_case="95", upper_case="102")]
    elif kind in {"multimetric-profile", "bubble-matrix"}:
        if kind == "multimetric-profile":
            spec.update(scale_min=0, scale_max=1, scale_note="Provided common score scale")
        rows = [dict(series=name, metric=metric, row=name, column=metric, value=str(value))
                for name, values in (("A", (0, .5, 1)), ("B", (.2, .4, .6)))
                for metric, value in zip(("I", "II", "III"), values)]
    elif kind in {"ridge-distribution", "qq-normal"}:
        rows = [dict(group=group, sample_id=f"{group}{index}", value=str(value))
                for group, values in (("A", (1, 2, 3, 4)), ("constant", (2, 2, 2))) for index, value in enumerate(values)]
    else:
        spec["bin_edges"] = [0, .5, 1]
        rows = [dict(model=model, sample_id=str(index), label=str(label), score=str(score))
                for model in ("A", "B") for index, (label, score) in enumerate(((0, 0), (0, .5), (1, .5), (1, 1)))]
    return spec, rows


class AdditionalChartChecks(unittest.TestCase):
    def test_ten_new_contracts_and_json_statistics(self):
        self.assertEqual(set(CHARTS.NEW_EXTENSIONS), {"hexbin-density", "density-contour", "coefficient-forest",
            "sensitivity-tornado", "multimetric-profile", "bubble-matrix", "ridge-distribution", "qq-normal",
            "calibration-curve", "spatial-point-values"})
        for kind in CHARTS.NEW_EXTENSIONS:
            with self.subTest(kind=kind):
                spec, rows = fixture(kind)
                stats = CHARTS.prepare_extension(spec, rows)["statistics"]
                self.assertEqual(stats["observations"], len(rows))
                self.assertFalse(stats["confidence_interval_calculated"])
                self.assertFalse(stats["missing_values_imputed"])
                json.dumps(stats, allow_nan=False)

    def test_missing_or_aliased_roles_fail_for_every_new_contract(self):
        for kind in CHARTS.NEW_EXTENSIONS:
            spec, rows = fixture(kind)
            role = CHARTS.NEW_EXTENSIONS[kind]["roles"][0]
            del rows[0][role]
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "column"):
                CHARTS.prepare_extension(spec, rows)
            spec, rows = fixture(kind)
            first, second = CHARTS.NEW_EXTENSIONS[kind]["roles"][:2]
            spec["roles"][second] = spec["roles"][first]
            with self.assertRaisesRegex(ValueError, "distinct"):
                CHARTS.prepare_extension(spec, rows)

    def test_numeric_values_reject_nonfinite_missing_and_empty(self):
        numeric = {"hexbin-density": "x", "density-contour": "y", "coefficient-forest": "lower",
                   "sensitivity-tornado": "upper_case", "multimetric-profile": "value", "bubble-matrix": "value",
                   "ridge-distribution": "value", "qq-normal": "value", "calibration-curve": "score", "spatial-point-values": "value"}
        for kind, role in numeric.items():
            for invalid in ("nan", "inf", "", None):
                spec, rows = fixture(kind)
                rows[0][role] = invalid
                with self.subTest(kind=kind, value=invalid), self.assertRaises(ValueError):
                    CHARTS.prepare_extension(spec, rows)

    def test_duplicates_are_never_silently_aggregated(self):
        for kind in CHARTS.NEW_EXTENSIONS:
            spec, rows = fixture(kind)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "Duplicate"):
                CHARTS.prepare_extension(spec, rows + [dict(rows[0])])

    def test_unknown_analysis_and_missing_unit_rejected(self):
        for kind in CHARTS.NEW_EXTENSIONS:
            spec, rows = fixture(kind)
            spec["normality_p_value"] = .01
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                CHARTS.prepare_extension(spec, rows)
            spec, rows = fixture(kind)
            if "axes" in spec:
                spec["axes"][next(iter(spec["axes"]))]["unit"] = ""
            elif "unit" in spec:
                spec["unit"] = ""
            else:
                continue
            with self.assertRaisesRegex(ValueError, "unit"):
                CHARTS.prepare_extension(spec, rows)

    def test_hexbin_and_contour_require_two_varying_axes(self):
        for kind in ("hexbin-density", "density-contour"):
            spec, rows = fixture(kind)
            for row in rows:
                row["y"] = "1"
            with self.assertRaisesRegex(ValueError, "variation"):
                CHARTS.prepare_extension(spec, rows)

    def test_binning_options_have_explicit_integer_limits(self):
        for kind, field, wrong in (("hexbin-density", "gridsize", (True, 3, 81, 4.5, "10")),
                                    ("density-contour", "bins", (True, 3, 61, 4.5, "10"))):
            for value in wrong:
                spec, rows = fixture(kind)
                spec[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    CHARTS.prepare_extension(spec, rows)

    def test_contour_histogram_conserves_counts_and_integrates_to_one(self):
        spec, rows = fixture("density-contour")
        bundle = CHARTS.prepare_extension(spec, rows)
        np.testing.assert_array_equal(bundle["counts"], np.eye(4))
        np.testing.assert_allclose(bundle["density"], np.eye(4) * 4 / 9)
        self.assertAlmostEqual(bundle["statistics"]["density_integral"], 1)
        self.assertFalse(bundle["statistics"]["kde_fit"])
        spec["density_method"] = "kde"
        with self.assertRaisesRegex(ValueError, "histogram"):
            CHARTS.prepare_extension(spec, rows)

    def test_forest_preserves_supplied_intervals_and_rejects_reversed_or_excluding(self):
        spec, rows = fixture("coefficient-forest")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        self.assertEqual(stats["supplied_intervals"], [[.2, -.3, .6000000000000001], [-.3, -.8, .10000000000000003]])
        self.assertFalse(stats["regression_fit_by_renderer"])
        for lower, upper in ((2, 1), (.3, .4)):
            damaged = copy.deepcopy(rows)
            damaged[0].update(lower=str(lower), upper=str(upper))
            with self.assertRaisesRegex(ValueError, "lower"):
                CHARTS.prepare_extension(spec, damaged)
        spec["reference_value"] = True
        with self.assertRaisesRegex(ValueError, "finite"):
            CHARTS.prepare_extension(spec, rows)

    def test_tornado_preserves_inverse_direction_and_requires_common_baseline(self):
        spec, rows = fixture("sensitivity-tornado")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        self.assertEqual(stats["outcome_differences"], [[10, -10], [-5, 2]])
        self.assertFalse(stats["parameter_scenarios_run_by_renderer"])
        rows[-1]["baseline"] = "101"
        with self.assertRaisesRegex(ValueError, "common"):
            CHARTS.prepare_extension(spec, rows)

    def test_profiles_keep_original_scale_without_hidden_normalization(self):
        spec, rows = fixture("multimetric-profile")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        self.assertEqual(stats["values"], [[0, .5, 1], [.2, .4, .6]])
        self.assertFalse(stats["normalization_performed"])
        self.assertFalse(stats["ranking_inferred"])
        with self.assertRaisesRegex(ValueError, "complete"):
            CHARTS.prepare_extension(spec, rows[:-1])
        for key, value in (("scale_min", True), ("scale_max", float("inf")), ("scale_min", 1)):
            altered = dict(spec, **{key: value})
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(altered, rows)
        rows[0]["value"] = "1.1"
        with self.assertRaisesRegex(ValueError, "scale"):
            CHARTS.prepare_extension(spec, rows)

    def test_signed_bubble_values_and_incomplete_cells_rejected(self):
        spec, rows = fixture("bubble-matrix")
        self.assertEqual(CHARTS.prepare_extension(spec, rows)["statistics"]["maximum_value"], 1)
        with self.assertRaisesRegex(ValueError, "complete"):
            CHARTS.prepare_extension(spec, rows[:-1])
        rows[0]["value"] = "-.1"
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            CHARTS.prepare_extension(spec, rows)

    def test_ridge_constant_groups_do_not_fabricate_density(self):
        spec, rows = fixture("ridge-distribution")
        bundle = CHARTS.prepare_extension(spec, rows)
        self.assertIsNone(bundle["densities"]["constant"])
        self.assertEqual(bundle["statistics"]["constant_groups"], ["constant"])
        self.assertTrue(np.all(bundle["densities"]["A"] > 0))

    def test_qq_midpoint_quantiles_and_reference_are_hand_checkable(self):
        spec, rows = fixture("qq-normal")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        curve = stats["quantiles"]["A"]
        self.assertEqual(curve["probabilities"], [.125, .375, .625, .875])
        self.assertEqual(curve["observed"], [1, 2, 3, 4])
        self.assertAlmostEqual(curve["standard_normal"][0], -1.150349380376008)
        self.assertAlmostEqual(curve["reference_sd"], np.sqrt(5 / 3))
        self.assertEqual(stats["quantiles"]["constant"]["reference_sd"], 0)
        self.assertFalse(stats["normality_assumed"])
        self.assertFalse(stats["normality_test_performed"])

    def test_calibration_assigns_boundary_and_probability_one_exactly(self):
        spec, rows = fixture("calibration-curve")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        model = stats["models"]["A"]
        self.assertEqual([item["n"] for item in model["bins"]], [1, 3])
        self.assertEqual(model["bins"][1]["mean_probability"], 2 / 3)
        self.assertEqual(model["bins"][1]["observed_fraction"], 2 / 3)
        self.assertEqual(model["brier_score"], .125)
        self.assertEqual(model["ece_for_declared_bins"], 0)
        self.assertFalse(stats["calibration_fit_by_renderer"])

    def test_calibration_empty_bins_null_and_not_assumed_zero(self):
        spec, rows = fixture("calibration-curve")
        spec["bin_edges"] = [0, .25, .5, .75, 1]
        bins = CHARTS.prepare_extension(spec, rows)["statistics"]["models"]["A"]["bins"]
        self.assertEqual(bins[1]["n"], 0)
        self.assertIsNone(bins[1]["mean_probability"])
        self.assertIsNone(bins[1]["observed_fraction"])

    def test_calibration_explicit_edges_probabilities_classes_and_cohort(self):
        for edges in (None, [0, 1], [0, .5, .5, 1], [0, .5, .9], [0, True, 1], [0, float("inf"), 1]):
            spec, rows = fixture("calibration-curve")
            spec["bin_edges"] = edges
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, rows)
        for role, value in (("score", "-.1"), ("score", "1.1"), ("label", "2"), ("sample_id", "different"), ("label", "0")):
            spec, rows = fixture("calibration-curve")
            rows[-1][role] = value
            with self.assertRaises(ValueError):
                CHARTS.prepare_extension(spec, rows)

    def test_planar_coordinates_equal_units_and_duplicate_locations(self):
        spec, rows = fixture("spatial-point-values")
        stats = CHARTS.prepare_extension(spec, rows)["statistics"]
        self.assertFalse(stats["basemap"])
        self.assertFalse(stats["spatial_interpolation"])
        spec["axes"]["y"]["unit"] = "km"
        with self.assertRaisesRegex(ValueError, "same unit"):
            CHARTS.prepare_extension(spec, rows)
        spec, rows = fixture("spatial-point-values")
        rows[-1].update(x=rows[0]["x"], y=rows[0]["y"])
        with self.assertRaisesRegex(ValueError, "Duplicate spatial"):
            CHARTS.prepare_extension(spec, rows)

    def test_lonlat_degree_axes_and_world_bounds(self):
        spec, rows = fixture("spatial-point-values")
        spec["coordinate_system"] = "lonlat"
        with self.assertRaisesRegex(ValueError, "degree"):
            CHARTS.prepare_extension(spec, rows)
        spec["axes"]["x"]["unit"] = spec["axes"]["y"]["unit"] = "degree"
        self.assertEqual(CHARTS.prepare_extension(spec, rows)["statistics"]["coordinate_system"], "lonlat")
        for axis, bad in (("x", "181"), ("y", "-91")):
            damaged = copy.deepcopy(rows)
            damaged[0][axis] = bad
            with self.assertRaisesRegex(ValueError, "Longitude"):
                CHARTS.prepare_extension(spec, damaged)

    def test_gallery_examples_are_all_checked_by_the_actual_main_renderer(self):
        main_spec = importlib.util.spec_from_file_location("main_chart_renderer", ROOT / "scripts/render_scientific_data.py")
        renderer = importlib.util.module_from_spec(main_spec)
        main_spec.loader.exec_module(renderer)
        self.assertEqual(len(renderer.SUPPORTED), 30)
        for kind in CHARTS.NEW_EXTENSIONS:
            spec, bundle, source = renderer.prepare(ROOT / "examples/scientific-figures/gallery" / (kind + ".json"))
            self.assertEqual(spec["template_id"], kind)
            self.assertEqual(source.suffix, ".csv")
            self.assertGreater(bundle["statistics"]["observations"], 1)

    @unittest.skipUnless(HAS_MPL, "Matplotlib is optional on validation-only hosts")
    def test_developer_limitations_remain_in_receipts_not_default_figure_text(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for kind in CHARTS.NEW_EXTENSIONS:
            spec, rows = fixture(kind)
            for field in ("interval_note", "scenario_note", "scale_note"):
                if field in spec:
                    spec[field] = "Provided study definition"
            bundle = CHARTS.prepare_extension(spec, rows)
            fig = CHARTS.render_extension(spec, bundle, plt)
            texts = [item.get_text() for item in fig.texts]
            for ax in fig.axes:
                texts.extend((ax.get_xlabel(), ax.get_ylabel(), ax.get_title()))
                if ax.get_legend():
                    texts.extend(item.get_text() for item in ax.get_legend().get_texts())
            visible = " ".join(texts).lower()
            for phrase in ("no normalization", "no basemap", "no solver", "no kde", "no fitted", "no scenario", "no model"):
                self.assertNotIn(phrase, visible)
            self.assertFalse(bundle["statistics"]["confidence_interval_calculated"])
            plt.close(fig)

    @unittest.skipUnless(HAS_MPL, "Matplotlib is optional on validation-only hosts")
    def test_ten_adapters_export_without_missing_glyphs_and_hexbin_conserves_counts(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for kind in CHARTS.NEW_EXTENSIONS:
            with self.subTest(kind=kind), warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                spec, rows = fixture(kind)
                bundle = CHARTS.prepare_extension(spec, rows)
                fig = CHARTS.render_extension(spec, bundle, plt)
                for suffix in ("png", "pdf", "svg"):
                    stream = io.BytesIO()
                    fig.savefig(stream, format=suffix, dpi=55, facecolor="white")
                    self.assertGreater(len(stream.getvalue()), 500)
                    if suffix == "pdf":
                        import pymupdf
                        with pymupdf.open(stream=stream.getvalue(), filetype="pdf") as document:
                            self.assertEqual(document[0].get_images(), [])
                            self.assertGreater(len(document[0].get_drawings()), 0)
                plt.close(fig)
                self.assertFalse([str(item.message) for item in captured if "Glyph" in str(item.message)])
                if kind == "hexbin-density":
                    self.assertEqual(bundle["statistics"]["rendered_hexagons"]["total"], len(rows))

    @unittest.skipUnless(HAS_MPL, "Matplotlib is optional on validation-only hosts")
    def test_actual_main_exports_vectors_and_copied_sources_reproduce_new_metrics(self):
        import pymupdf
        main_spec = importlib.util.spec_from_file_location("reproducible_more_charts", ROOT / "scripts/render_scientific_data.py")
        renderer = importlib.util.module_from_spec(main_spec)
        main_spec.loader.exec_module(renderer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec, rows = fixture("calibration-curve")
            source = root / "data.csv"
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            manifest = root / "contract.json"
            manifest.write_text(json.dumps(spec), encoding="utf-8")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            report = renderer.render(manifest, root / "original")
            self.assertEqual(report["input_sha256"], source_hash)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
            for name in ("render_scientific_data.py", "scientific_chart_extensions.py", "data.csv", "contract.json"):
                self.assertTrue((root / "original/reproduce" / name).is_file())
            with pymupdf.open(root / "original/figure.pdf") as document:
                self.assertEqual(len(document), 1)
                self.assertEqual(document[0].get_images(), [])
                self.assertGreater(len(document[0].get_drawings()), 0)
                self.assertIn("Brier", document[0].get_text())
            run = subprocess.run([sys.executable, "-X", "utf8", str(root / "original/reproduce/render_scientific_data.py"),
                                  "--manifest", str(root / "original/reproduce/contract.json"), "--output", str(root / "reproduced")],
                                 capture_output=True, encoding="utf-8", timeout=180)
            self.assertEqual(run.returncode, 0, run.stderr[-1500:])
            reproduced = json.loads((root / "reproduced/figure-data.json").read_text(encoding="utf-8"))
            self.assertEqual(report["statistics"], reproduced["statistics"])
            self.assertEqual(report["outputs"]["png"]["sha256"], reproduced["outputs"]["png"]["sha256"])


if __name__ == "__main__":
    unittest.main()
