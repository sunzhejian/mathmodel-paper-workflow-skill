import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
