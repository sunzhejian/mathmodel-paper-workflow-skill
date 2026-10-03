import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_scientific_data", ROOT / "scripts/render_scientific_data.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
DEMO_SPEC = importlib.util.spec_from_file_location("generate_advanced_figure_examples", ROOT / "scripts/generate_advanced_figure_examples.py")
DEMO = importlib.util.module_from_spec(DEMO_SPEC)
DEMO_SPEC.loader.exec_module(DEMO)
HAS_MPL = importlib.util.find_spec("matplotlib") is not None
CJK_DIR = os.environ.get("MATHMODEL_CJK_FONT_DIR")


class ScientificDataChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = DEMO.inputs(self.root / "inputs")

    def tearDown(self):
        self.temp.cleanup()

    def rewrite(self, index, update):
        path = self.inputs[index]
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(update)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_actual_pairs_define_metrics_and_constant_truth_has_no_r2(self):
        value = MODULE.regression_metrics([1, 2, 3], [2, 2, 2])
        self.assertAlmostEqual(value["rmse"], np.sqrt(2 / 3))
        self.assertAlmostEqual(value["mae"], 2 / 3)
        self.assertEqual(value["r2"], 0)
        self.assertIsNone(MODULE.regression_metrics([2, 2], [1, 3])["r2"])
        self.assertLess(MODULE.regression_metrics([1, 2], [10, 10])["r2"], 0)

    def test_labels_units_and_synthetic_status_are_explicit(self):
        path = self.rewrite(0, {"data_kind": None})
        with self.assertRaisesRegex(ValueError, "data_kind"):
            MODULE.prepare(path)
        path = self.rewrite(0, {"data_kind": "real", "columns": [{"key":"a","label":"A","unit":"1"}, {"key":"b","label":"B"}]})
        with self.assertRaisesRegex(ValueError, "unit"):
            MODULE.prepare(path)

    def test_unknown_analysis_fields_cannot_be_silently_ignored(self):
        path = self.rewrite(0, {"add_significance_stars": True})
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            MODULE.prepare(path)

    def test_correlation_uses_selected_raw_values_and_source_is_unchanged(self):
        source = self.root / "inputs/features.csv"
        before = source.read_bytes()
        _, data, _ = MODULE.prepare(self.inputs[0])
        values = data["values"]
        np.testing.assert_allclose(data["statistics"]["correlation"], np.corrcoef(values, rowvar=False))
        self.assertFalse(data["statistics"]["standardized"])
        self.assertEqual(source.read_bytes(), before)

    def test_missing_or_nonfinite_data_is_not_filled(self):
        source = self.root / "inputs/features.csv"
        for value in ("", "NaN"):
            with self.subTest(value=value):
                source.write_text("a,b,c,d\n" + value + ",1,2,3\n1,2,3,4\n2,3,4,5\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.inputs[0])

    def test_same_model_sample_cannot_move_between_splits(self):
        source = self.root / "inputs/predictions.csv"
        with source.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows.append(dict(rows[0], split="test"))
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, "multiple splits"):
            MODULE.prepare(self.inputs[1])

    def test_model_comparison_cannot_hide_different_cohorts(self):
        source = self.root / "inputs/predictions.csv"
        with source.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows.pop()
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, "same sample IDs"):
            MODULE.prepare(self.inputs[1])
        spec, bundle, _ = MODULE.prepare(self.rewrite(1, {"comparison": False}))
        self.assertFalse(bundle["statistics"]["comparison"])

    def test_surface_values_are_supplied_not_an_analytic_blend(self):
        _, bundle, _ = MODULE.prepare(self.inputs[2])
        with (self.root / "inputs/response-grid.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        expected = {(float(row["x"]), float(row["y"])):float(row["z"]) for row in rows}
        for j, y in enumerate(bundle["y"]):
            for i, x in enumerate(bundle["x"]):
                self.assertEqual(bundle["z"][j, i], expected[(x, y)])
        self.assertFalse(bundle["statistics"]["optimizer_run_by_renderer"])

    def test_sparse_and_duplicate_surfaces_are_rejected(self):
        source = self.root / "inputs/response-grid.csv"
        original = source.read_text(encoding="utf-8").splitlines()
        for lines in (original[:-1], original + [original[-1]]):
            source.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.prepare(self.inputs[2])

    def test_existing_output_is_preserved_before_any_drawing(self):
        folder = self.root / "existing"
        folder.mkdir()
        file = folder / "figure.png"
        file.write_bytes(b"existing user figure")
        with self.assertRaisesRegex(ValueError, "new output"):
            MODULE.render(self.inputs[0], folder)
        self.assertEqual(file.read_bytes(), b"existing user figure")

    def test_sparse_trial_plot_preserves_observed_points_without_a_surface(self):
        source = self.root / "inputs/response-grid.csv"
        source.write_text("x,y,z\n1,1,0.8\n2,3,0.2\n1,1,0.9\n", encoding="utf-8")
        _, bundle, _ = MODULE.prepare(self.rewrite(2, {"surface_mode": "scatter"}))
        self.assertEqual(bundle["statistics"]["samples"], 3)
        self.assertEqual(bundle["mode"], "scatter")
        np.testing.assert_array_equal(bundle["values"], [[1, 1, .8], [2, 3, .2], [1, 1, .9]])

    @unittest.skipUnless(HAS_MPL, "Optional Matplotlib route not installed")
    def test_three_real_renderers_produce_vectors_inputs_and_computed_reports(self):
        for index, manifest in enumerate(self.inputs):
            with self.subTest(index=index):
                # ASCII data labels in this platform-independent mechanics test.
                spec = json.loads(manifest.read_text(encoding="utf-8"))
                spec["title"] = "Synthetic source-bound figure"
                if "columns" in spec:
                    for role in spec["columns"]:
                        role["label"] = role["key"]
                for role in ("x", "y", "z"):
                    if role in spec:
                        spec[role]["label"] = role
                manifest.write_text(json.dumps(spec), encoding="utf-8")
                if index == 1:
                    source = self.root / "inputs/predictions.csv"
                    source.write_text(source.read_text(encoding="utf-8").replace("示例方案 A", "Case A").replace("示例方案 B", "Case B"), encoding="utf-8")
                report = MODULE.render(manifest, self.root / f"render-{index}")
                folder = self.root / f"render-{index}"
                self.assertEqual(report["data_kind"], "synthetic")
                self.assertEqual(report["input_sha256"], hashlib.sha256((folder / "reproduce/data.csv").read_bytes()).hexdigest())
                self.assertTrue((folder / "reproduce/render_scientific_data.py").is_file())
                ET.parse(folder / "figure.svg")
                with pymupdf.open(folder / "figure.pdf") as pdf:
                    self.assertEqual(len(pdf), 1)
                    self.assertGreater(len(pdf[0].get_text()), 20)
                    self.assertEqual(pdf[0].get_images(), [])
                if index == 1:
                    _, bundle, _ = MODULE.prepare(manifest)
                    self.assertEqual(report["statistics"], bundle["statistics"])

    @unittest.skipUnless(HAS_MPL and CJK_DIR, "Matplotlib or explicit CJK font directory unavailable")
    def test_chinese_cli_render_closes_font_files_and_exports_text(self):
        folder = self.root / "chinese"
        run = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/render_scientific_data.py"),
                              "--manifest", str(self.inputs[0]), "--output", str(folder),
                              "--font", str(Path(CJK_DIR) / "NotoSansSC.ttf")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        self.assertEqual(run.returncode, 0, run.stderr[-1500:])
        self.assertEqual(json.loads(run.stdout)["data_kind"], "synthetic")
        with pymupdf.open(folder / "figure.pdf") as pdf:
            self.assertIn("多变量关系与分布", pdf[0].get_text())
        report = json.loads((folder / "figure-data.json").read_text(encoding="utf-8"))
        self.assertEqual(report["font"]["variable_weights_instantiated"], [400, 700])
        # The child has ended; Windows can now rename these private font files.
        fonts = list((folder / ".fonts").glob("*.ttf"))
        self.assertTrue(fonts)
        for path in fonts:
            target = path.with_suffix(".checked")
            path.rename(target)
            target.rename(path)


class PairedAndBinaryDataChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("paired.json", "paired-values.csv", "binary-roc.json", "binary-scores.csv"):
            shutil.copy2(ROOT / "examples/scientific-figures" / name, self.root / name)

    def tearDown(self):
        self.temp.cleanup()

    def contract(self, name, **changes):
        path = self.root / name
        spec = json.loads(path.read_text(encoding="utf-8"))
        spec.update(changes)
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def rows(self, name):
        with (self.root / name).open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def write_rows(self, name, rows):
        with (self.root / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_pairs_align_by_id_not_csv_row_position(self):
        self.write_rows("paired-values.csv", [
            {"sample_id": "S1", "condition": "After", "value": 20},
            {"sample_id": "S2", "condition": "Before", "value": 2},
            {"sample_id": "S2", "condition": "After", "value": 4},
            {"sample_id": "S1", "condition": "Before", "value": 10},
        ])
        path = self.contract("paired.json", conditions=["Before", "After"])
        _, bundle, _ = MODULE.prepare(path)
        self.assertEqual(bundle["sample_ids"], ["S1", "S2"])
        np.testing.assert_array_equal(bundle["values"], [[10, 20], [2, 4]])
        self.assertEqual(bundle["statistics"]["paired_difference"]["mean"], 6)
        self.assertAlmostEqual(bundle["statistics"]["paired_difference"]["sd"], np.sqrt(32))
        original_stats = bundle["statistics"]
        self.write_rows("paired-values.csv", self.rows("paired-values.csv")[::-1])
        self.assertEqual(MODULE.prepare(path)[1]["statistics"], original_stats)
        _, reverse, _ = MODULE.prepare(self.contract("paired.json", conditions=["After", "Before"]))
        self.assertEqual(reverse["statistics"]["paired_difference"]["mean"], -6)
        self.assertFalse(reverse["statistics"]["p_value_calculated"])
        self.assertFalse(reverse["statistics"]["confidence_interval_calculated"])

    def test_pair_missing_duplicate_unknown_or_empty_id_is_rejected(self):
        rows = self.rows("paired-values.csv")
        cases = [rows[:-1], rows + [dict(rows[0])],
                 [dict(rows[0], condition="Unknown stage")] + rows[1:],
                 [dict(rows[0], sample_id="")] + rows[1:]]
        for sample in cases:
            with self.subTest(sample=sample[:1]):
                self.write_rows("paired-values.csv", sample)
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.root / "paired.json")

    def test_pair_nonfinite_values_and_unknown_contract_fields_are_rejected(self):
        original = self.rows("paired-values.csv")
        for value in ("", "NaN", "inf", "1e309"):
            with self.subTest(value=value):
                self.write_rows("paired-values.csv", [dict(original[0], value=value)] + original[1:])
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.root / "paired.json")
        self.write_rows("paired-values.csv", original)
        for changes in ({"conditions": ["阶段一"]}, {"unit": ""},
                        {"roles": {"sample_id": "sample_id", "condition": "condition", "value": "value", "group": "group"}},
                        {"p_value": .01}):
            with self.subTest(changes=changes):
                shutil.copy2(ROOT / "examples/scientific-figures/paired.json", self.root / "paired.json")
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.contract("paired.json", **changes))

    def test_constant_pairs_have_real_difference_and_no_kde(self):
        rows = [{"sample_id": sample, "condition": condition, "value": value}
                for sample in ("A", "B", "C") for condition, value in (("Before", 5), ("After", 7))]
        self.write_rows("paired-values.csv", rows)
        _, bundle, _ = MODULE.prepare(self.contract("paired.json", conditions=["Before", "After"]))
        self.assertEqual(bundle["statistics"]["constant_conditions"], ["Before", "After"])
        self.assertEqual(bundle["statistics"]["paired_difference"], {"mean": 2., "median": 2., "sd": 0.})
        self.assertIsNone(MODULE.density(bundle["values"][:, 0], np.linspace(4, 8, 30)))

    def test_pair_calculation_overflow_is_rejected(self):
        self.write_rows("paired-values.csv", [{"sample_id": sample, "condition": condition, "value": value}
                for sample in ("A", "B") for condition, value in (("Before", -1e308), ("After", 1e308))])
        with self.assertRaisesRegex(ValueError, "finite numeric range"):
            MODULE.prepare(self.contract("paired.json", conditions=["Before", "After"]))

    def test_roc_perfect_reverse_and_constant_scores_have_known_auc(self):
        labels = [0, 0, 1, 1]
        perfect = MODULE.binary_roc(labels, [.1, .2, .8, .9])
        reverse = MODULE.binary_roc(labels, [.9, .8, .2, .1])
        constant = MODULE.binary_roc(labels, [.5] * 4)
        self.assertEqual(perfect["auc"], 1.)
        self.assertEqual(reverse["auc"], 0.)
        self.assertEqual(constant["auc"], .5)
        self.assertEqual(constant["fpr"], [0., 1.])
        self.assertEqual(constant["tpr"], [0., 1.])
        self.assertEqual(constant["thresholds"], [None, .5])

    def test_roc_ties_move_as_whole_groups_independent_of_row_order(self):
        labels, scores = [0, 1, 0, 1], [.8, .8, .2, .2]
        result = MODULE.binary_roc(labels, scores)
        self.assertEqual(result["fpr"], [0., .5, 1.])
        self.assertEqual(result["tpr"], [0., .5, 1.])
        self.assertEqual(result["auc"], .5)
        self.assertEqual(result["thresholds"], [None, .8, .2])
        order = [1, 0, 3, 2]
        self.assertEqual(result, MODULE.binary_roc([labels[i] for i in order], [scores[i] for i in order]))

    def test_auc_matches_independent_pairwise_ranking_with_half_credit_for_ties(self):
        labels = np.array([0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0])
        for scores in ([3, 1, 2, 3, 0, 2, 1, 2, 3, 1, 0],
                       [7, -2, 1, 5, 0, 6, 8, 2, 3, 4, -1]):
            values = np.array(scores)
            positive, negative = values[labels == 1], values[labels == 0]
            expected = sum(float(a > b) + .5 * float(a == b) for a in positive for b in negative) / (len(positive) * len(negative))
            result = MODULE.binary_roc(labels, values)
            self.assertAlmostEqual(result["auc"], expected)
            transformed = MODULE.binary_roc(labels, values * 3 + 11)
            self.assertEqual(result["fpr"], transformed["fpr"])
            self.assertEqual(result["tpr"], transformed["tpr"])
            self.assertAlmostEqual(MODULE.binary_roc(labels, -values)["auc"], 1 - expected)

    def test_roc_single_class_invalid_labels_nonfinite_or_misaligned_values_rejected(self):
        for labels, scores in (([0, 0], [.1, .9]), ([1, 1], [.1, .9]), ([0, 2], [.1, .9]),
                               ([0, 1], [.1, float("nan")]), ([0, 1], [float("inf"), .1]),
                               ([0, 1], [.1]), ([0, float("nan")], [.1, .9])):
            with self.subTest(labels=labels, scores=scores):
                with self.assertRaises(ValueError):
                    MODULE.binary_roc(labels, scores)

    def test_roc_different_cohorts_labels_duplicates_and_invalid_csv_values_rejected(self):
        original = self.rows("binary-scores.csv")
        model_b = next(i for i, row in enumerate(original) if row["model"] == "方案B")
        cases = [original[:model_b] + original[model_b + 1:], original + [dict(original[0])],
                 [dict(row, label="1") if i == model_b else row for i, row in enumerate(original)],
                 [dict(row, label="2") if i == 0 else row for i, row in enumerate(original)],
                 [dict(row, score="NaN") if i == 0 else row for i, row in enumerate(original)],
                 [dict(row, sample_id="") if i == 0 else row for i, row in enumerate(original)],
                 [dict(row, label="0") for row in original]]
        for rows in cases:
            with self.subTest(rows=rows[:1]):
                self.write_rows("binary-scores.csv", rows)
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.root / "binary-roc.json")

    def test_roc_contract_does_not_accept_unimplemented_cv_or_ci_requests(self):
        for changes in ({"fold_id": "fold"}, {"confidence_level": .95}, {"comparison": False},
                        {"roles": {"model": "model", "sample_id": "sample_id", "label": "label", "score": "label"}}):
            with self.subTest(changes=changes):
                shutil.copy2(ROOT / "examples/scientific-figures/binary-roc.json", self.root / "binary-roc.json")
                with self.assertRaises(ValueError):
                    MODULE.prepare(self.contract("binary-roc.json", **changes))

    def test_new_interfaces_preserve_sources_and_report_computed_statistics(self):
        for manifest, data_file in (("paired.json", "paired-values.csv"), ("binary-roc.json", "binary-scores.csv")):
            before = (self.root / data_file).read_bytes()
            spec, bundle, source = MODULE.prepare(self.root / manifest)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(spec["data_kind"], "synthetic")
            self.assertFalse(bundle["statistics"]["confidence_interval_calculated"])
        _, bundle, _ = MODULE.prepare(self.root / "binary-roc.json")
        self.assertTrue(bundle["statistics"]["same_cohort_verified"])
        self.assertEqual(bundle["statistics"]["models"]["方案C"]["auc"], .5)
        self.assertFalse(bundle["statistics"]["training_run_by_renderer"])

    @unittest.skipUnless(HAS_MPL, "Optional Matplotlib route not installed")
    def test_new_figures_and_reproduction_export_real_vectors_and_matching_statistics(self):
        for index, name in enumerate(("paired.json", "binary-roc.json")):
            with self.subTest(template=name):
                manifest = self.contract(name, title="Synthetic data interface figure")
                if index == 0:
                    manifest = self.contract(name, conditions=["Before", "After"])
                    source = self.root / "paired-values.csv"
                    source.write_text(source.read_text(encoding="utf-8").replace("阶段一", "Before").replace("阶段二", "After"), encoding="utf-8")
                else:
                    source = self.root / "binary-scores.csv"
                    source.write_text(source.read_text(encoding="utf-8").replace("方案A", "Case A").replace("方案B", "Case B").replace("方案C", "Case C"), encoding="utf-8")
                output = self.root / f"figure-{index}"
                report = MODULE.render(manifest, output)
                ET.parse(output / "figure.svg")
                with pymupdf.open(output / "figure.pdf") as pdf:
                    self.assertGreater(len(pdf[0].get_text()), 50)
                    self.assertEqual(pdf[0].get_images(), [])
                self.assertEqual(report["input_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                rebuilt = self.root / f"rebuilt-{index}"
                result = subprocess.run([sys.executable, "-X", "utf8", str(output / "reproduce/render_scientific_data.py"),
                                         "--manifest", str(output / "reproduce/contract.json"), "--output", str(rebuilt)],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr[-1500:])
                rebuilt_report = json.loads((rebuilt / "figure-data.json").read_text(encoding="utf-8"))
                self.assertEqual(rebuilt_report["statistics"], report["statistics"])
                self.assertEqual(rebuilt_report["input_sha256"], report["input_sha256"])
                for extension in ("png", "pdf", "svg"):
                    self.assertGreater((rebuilt / ("figure." + extension)).stat().st_size, 1000)

    @unittest.skipUnless(HAS_MPL, "Optional Matplotlib route not installed")
    def test_constant_paired_conditions_render_without_kde_or_invented_significance(self):
        self.write_rows("paired-values.csv", [{"sample_id": sample, "condition": condition, "value": value}
                for sample in ("A", "B", "C") for condition, value in (("Before", 5), ("After", 7))])
        manifest = self.contract("paired.json", title="Constant synthetic pairs", conditions=["Before", "After"])
        report = MODULE.render(manifest, self.root / "constant-figure")
        self.assertEqual(report["statistics"]["constant_conditions"], ["Before", "After"])
        with pymupdf.open(self.root / "constant-figure/figure.pdf") as pdf:
            self.assertIn("KDE omitted", pdf[0].get_text())
            self.assertNotIn("p<", pdf[0].get_text())


if __name__ == "__main__":
    unittest.main()
