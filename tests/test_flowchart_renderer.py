"""Behavioral checks for the explicit-coordinate schematic renderer."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location("flowchart", ROOT / "scripts/render_flowchart.py")
m = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(m)


def basic():
    return {
        "schema_version": 1, "title": "流程机制", "claim": "阶段输入通过处理产生输出。",
        "source_note": "匿名测试示例，无求解运行证据。", "data_kind": "schematic",
        "canvas": {"width": 400, "height": 450},
        "nodes": [
            {"id": "input", "label": "输入", "kind": "input", "x": 100, "y": 20, "width": 200, "height": 60},
            {"id": "process", "label": "处理", "kind": "process", "x": 100, "y": 170, "width": 200, "height": 60},
            {"id": "output", "label": "输出", "kind": "output", "x": 100, "y": 320, "width": 200, "height": 60},
        ],
        "edges": [{"id": "e1", "source": "input", "target": "process"},
                  {"id": "e2", "source": "process", "target": "output"}],
        "groups": [],
    }


class FlowchartRendererTests(unittest.TestCase):
    def test_example_contracts_preserve_topology_and_publication_fonts(self):
        paths = list((ROOT / "examples/flowcharts").glob("*.json"))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(example=path.name):
                supplied = m.read_manifest(path)
                original = copy.deepcopy(supplied)
                spec, preflight = m.prepare(supplied)
                self.assertEqual(supplied, original, "validation must not mutate caller contracts")
                tree = ET.fromstring(m.make_drawio(spec, preflight))
                cells = {cell.attrib["id"]: cell for cell in tree.iter("mxCell")}
                for edge in supplied["edges"]:
                    self.assertEqual(cells[edge["id"]].attrib["source"], edge["source"])
                    self.assertEqual(cells[edge["id"]].attrib["target"], edge["target"])
                    self.assertEqual(cells[edge["id"]].attrib["value"], edge.get("label", ""))
                self.assertGreaterEqual(preflight["effective_font_pt_at_publication_width"], 8.5)
                self.assertFalse(preflight["warnings"])

    def test_unknown_fields_are_rejected_at_each_contract_level(self):
        locations = [lambda s: s, lambda s: s["nodes"][0], lambda s: s["edges"][0],
                     lambda s: s.setdefault("style", {}), lambda s: s["canvas"]]
        for location in locations:
            spec = basic()
            location(spec)["smart_layout"] = True
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, "unknown fields"):
                    m.prepare(spec)

    def test_duplicate_json_keys_are_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "input.json"
            manifest.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
                m.read_manifest(manifest)

    def test_duplicate_ids_across_node_edge_layers_are_rejected(self):
        spec = basic()
        spec["edges"][0]["id"] = spec["nodes"][0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate or reserved id"):
            m.prepare(spec)

    def test_absent_endpoint_is_rejected(self):
        spec = basic()
        spec["edges"][0]["target"] = "absent_node"
        with self.assertRaisesRegex(ValueError, "missing target endpoint"):
            m.prepare(spec)

    def test_invalid_geometry_is_rejected(self):
        for value in (-1, True, "80", float("nan"), float("inf"), None):
            spec = basic()
            spec["nodes"][0]["width"] = value
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    m.prepare(spec)

    def test_invalid_enum_types_produce_clear_contract_errors(self):
        for field, value in (("kind", []), ("relation", {}), ("side", [])):
            spec = basic()
            if field == "kind":
                spec["nodes"][0][field] = value
            elif field == "relation":
                spec["edges"][0][field] = value
            else:
                spec["edges"][0]["source_port"] = {"side": value}
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    m.prepare(spec)

    def test_non_schematic_content_is_not_treated_as_observed_data(self):
        spec = basic()
        spec["data_kind"] = "real"
        with self.assertRaisesRegex(ValueError, "schematic"):
            m.prepare(spec)

    def test_diamond_requires_a_visible_condition(self):
        spec = basic()
        spec["nodes"][1].update({"kind": "decision", "height": 130})
        with self.assertRaisesRegex(ValueError, "condition_label"):
            m.prepare(spec)

    def test_ambiguous_decision_branches_are_rejected(self):
        spec = m.read_manifest(ROOT / "examples/flowcharts/optimization_feedback.json")
        branches = [edge for edge in spec["edges"] if edge["source"] == "feasibility"]
        branches[0].pop("label")
        with self.assertRaisesRegex(ValueError, "distinctly labeled branches"):
            m.prepare(spec)

    def test_nonbinary_decision_can_use_three_meaningful_labels(self):
        spec = {
            "schema_version": 1, "title": "分类机制", "claim": "显式条件具有三个互异分支。",
            "source_note": "分类示例", "data_kind": "schematic", "canvas": {"width": 800, "height": 420},
            "nodes": [
                {"id": "decision", "label": "类别判定", "kind": "decision", "condition_label": "由规则 R 判断",
                 "x": 250, "y": 20, "width": 300, "height": 140},
                {"id": "low", "label": "低区间", "kind": "process", "x": 40, "y": 300, "width": 200, "height": 60},
                {"id": "mid", "label": "中区间", "kind": "process", "x": 300, "y": 300, "width": 200, "height": 60},
                {"id": "high", "label": "高区间", "kind": "process", "x": 560, "y": 300, "width": 200, "height": 60},
            ],
            "edges": [
                {"id": "low_branch", "source": "decision", "target": "low", "label": "低区间",
                 "source_port": {"side": "west"}, "target_port": {"side": "north"},
                 "waypoints": [{"x": 140, "y": 90}], "label_position": .75},
                {"id": "mid_branch", "source": "decision", "target": "mid", "label": "中区间"},
                {"id": "high_branch", "source": "decision", "target": "high", "label": "高区间",
                 "source_port": {"side": "east"}, "target_port": {"side": "north"},
                 "waypoints": [{"x": 660, "y": 90}], "label_position": .75},
            ],
        }
        validated, _ = m.prepare(spec)
        self.assertEqual({edge["label"] for edge in validated["edges"]}, {"低区间", "中区间", "高区间"})

    def test_loop_requires_an_authored_lane(self):
        spec = basic()
        spec["edges"][1].update({"target": "input", "relation": "feedback"})
        with self.assertRaisesRegex(ValueError, "explicit lane waypoints"):
            m.prepare(spec)

    def test_route_through_a_third_node_is_rejected(self):
        spec = basic()
        spec["edges"] = [{"id": "shortcut", "source": "input", "target": "output"}]
        with self.assertRaisesRegex(ValueError, "crosses unrelated node process"):
            m.prepare(spec)

    def test_misdeclared_port_cannot_send_a_lane_through_its_source(self):
        spec = basic()
        spec["edges"][0].update({"source_port": {"side": "north"},
                                 "waypoints": [{"x": 200, "y": 100}]})
        with self.assertRaisesRegex(ValueError, "crosses its endpoint shape input"):
            m.prepare(spec)

    def test_group_heading_has_a_reserved_text_lane(self):
        spec = m.read_manifest(ROOT / "examples/flowcharts/numerical_iteration.json")
        spec["groups"][0]["label"] = "时间推进与内层迭代（机制示意）"
        with self.assertRaisesRegex(ValueError, "connector covers group heading"):
            m.prepare(spec)

    def test_group_border_cannot_run_through_a_branch_label(self):
        spec = m.read_manifest(ROOT / "examples/flowcharts/numerical_iteration.json")
        next(edge for edge in spec["edges"] if edge["id"] == "finish")["label_position"] = .5
        with self.assertRaisesRegex(ValueError, "branch label crosses group border"):
            m.prepare(spec)

    def test_diagonal_lane_hits_are_detected(self):
        self.assertTrue(m.segment_hits_rect((0, 0), (100, 100), (40, 40, 60, 60)))
        self.assertFalse(m.segment_hits_rect((0, 0), (100, 100), (40, 70, 60, 90)))

    def test_branch_label_cannot_cover_a_node(self):
        spec = basic()
        spec["edges"][0].update({"label": "输入", "label_position": 0, "label_offset": {"x": 0, "y": -25}})
        with self.assertRaisesRegex(ValueError, "branch label covers node input"):
            m.prepare(spec)

    def test_unreadable_projected_font_is_rejected(self):
        spec = basic()
        spec["canvas"]["width"] = 1800
        with self.assertRaisesRegex(ValueError, "Font becomes"):
            m.prepare(spec)

    def test_cjk_and_diamond_text_budgets_fail_before_source_write(self):
        spec = basic()
        spec["nodes"][0]["label"] = "很长的输入名称" * 8
        with self.assertRaisesRegex(ValueError, "text budget exceeded"):
            m.prepare(spec)

    def test_plain_comparison_symbols_survive_as_editable_text(self):
        spec = basic()
        spec["nodes"][1]["label"] = "x < 3 & y > 1"
        validated, preflight = m.prepare(spec)
        data = m.make_drawio(validated, preflight)
        self.assertIn(b"&lt;", data)
        cells = {cell.attrib["id"]: cell for cell in ET.fromstring(data).iter("mxCell")}
        self.assertEqual(cells["process"].attrib["value"], "x < 3 & y > 1")
        self.assertIn("html=0", cells["process"].attrib["style"])
        self.assertEqual(cells["process"].attrib["parent"], "mm-layer-nodes")
        self.assertEqual(cells["e1"].attrib["parent"], "mm-layer-connectors")
        self.assertIn("whiteSpace=nowrap", cells["e1"].attrib["style"])

    def test_output_directory_and_source_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            manifest = base / "input.json"
            manifest.write_text(json.dumps(basic(), ensure_ascii=False), encoding="utf-8")
            source_before = manifest.read_bytes()
            output = base / "new-output"
            result = m.render(manifest, output)
            self.assertEqual(result["status"], "source_only")
            self.assertEqual(result["visual_review"], "pending")
            self.assertTrue((output / "figure.drawio").exists())
            self.assertEqual(manifest.read_bytes(), source_before)
            artifact_before = (output / "figure.drawio").read_bytes()
            with self.assertRaisesRegex(ValueError, "NEW directory"):
                m.render(manifest, output)
            self.assertEqual((output / "figure.drawio").read_bytes(), artifact_before)

    def test_validation_failure_does_not_create_output_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            spec = basic()
            spec["edges"][0]["target"] = "absent"
            manifest = base / "input.json"
            manifest.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(ValueError):
                m.render(manifest, base / "should-not-exist")
            self.assertFalse((base / "should-not-exist").exists())

    def test_actual_export_failure_preserves_source_and_failure_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            manifest = base / "input.json"
            manifest.write_text(json.dumps(basic()), encoding="utf-8")
            exe = base / "drawio.exe"
            exe.write_bytes(b"test-only")
            with patch.object(m.subprocess, "run", return_value=Mock(returncode=1)):
                with self.assertRaisesRegex(RuntimeError, "preserved source and report"):
                    m.render(manifest, base / "output", drawio=exe)
            receipt = json.loads((base / "output/rendering_report.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "export_failed")
            self.assertEqual(receipt["visual_review"], "pending")
            self.assertFalse(receipt["exports"][0]["output_written"])
            self.assertTrue((base / "output/figure.drawio").exists())

    def test_svg_export_is_not_marked_universally_portable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "figure.svg"
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>', encoding="utf-8")
            report = m._svg_report(path)
            self.assertFalse(report["universal_direct_embedding_supported"])
            self.assertIn("foreignObject", report["known_typst_hazards"][0])
            self.assertEqual(report["typst_asset"], "figure.png")

    def test_scale_below_three_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "input.json"
            manifest.write_text(json.dumps(basic()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least 3"):
                m.render(manifest, Path(folder) / "new-output", scale=2)


if __name__ == "__main__":
    unittest.main()
