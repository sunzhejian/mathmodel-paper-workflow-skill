"""Render an explicit schematic contract to layered, editable draw.io objects.

This adapter uses authored coordinates, not automatic smart layout. A declared
source or a rendered algorithm is not evidence of scientific validity or execution.
Run --help for the CLI; examples/flowcharts contains reusable contract examples.
Only the Python standard library is needed for source generation. Renderer exports
require an explicitly selected draw.io executable; PDF inspection uses PyMuPDF
when available. The actual manuscript must still be rendered and inspected.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET


VERSION = "1.0"
KINDS = {"input", "output", "process", "decision", "start", "end", "annotation"}
RELATIONS = {"process", "data", "condition", "feedback", "loop", "association"}
SIDES = {"north": (0.5, 0), "east": (1, 0.5),
         "south": (0.5, 1), "west": (0, 0.5)}
TOP_FIELDS = {"schema_version", "title", "claim", "source_note", "data_kind",
              "nodes", "edges", "groups", "canvas", "style"}
NODE_FIELDS = {"id", "label", "kind", "x", "y", "width", "height", "group",
               "condition_label", "source_ref"}
EDGE_FIELDS = {"id", "source", "target", "label", "relation", "waypoints",
               "source_port", "target_port", "label_position", "label_offset",
               "source_ref"}
GROUP_FIELDS = {"id", "label", "x", "y", "width", "height", "source_ref"}
STYLE_FIELDS = {"font_family", "font_size", "publication_width_mm",
                "minimum_font_pt", "maximum_height_mm", "minimum_dpi"}


def _object(value, allowed, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected an object")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown fields: {', '.join(sorted(unknown))}")


def _text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: nonempty text required")
    if any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF
           or ord(c) in {0xFFFE, 0xFFFF} for c in value):
        raise ValueError(f"{where}: invalid XML/control character")
    return value


def _number(value, where, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f"{where}: {'positive' if positive else 'nonnegative'} finite number required")
    return float(value)


def _geometry(item, where):
    for key in ("x", "y", "width", "height"):
        _number(item.get(key), f"{where}.{key}", positive=key in {"width", "height"})


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def read_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)


def node_text(node):
    text = node["label"]
    if node["kind"] == "decision" and node["condition_label"] not in text:
        text += "\n" + node["condition_label"]
    return text


def text_width(text, size):
    """Conservative width estimate; actual font metrics still require visual review."""
    total = 0.0
    for char in text:
        if unicodedata.combining(char):
            continue
        if char == "\t":
            total += 2 * size
        elif unicodedata.east_asian_width(char) in {"W", "F", "A"}:
            total += size
        else:
            total += size * 0.56
    return total


def _text_budget(text, width, height, size, where):
    lines = text.split("\n")
    needed_width = max(text_width(line, size) for line in lines)
    needed_height = len(lines) * (size + 3)
    if needed_width > width + 0.01 or needed_height > height + 0.01:
        raise ValueError(f"{where}: text budget exceeded ({needed_width:.1f} x "
                         f"{needed_height:.1f}; available {width:.1f} x {height:.1f}). "
                         "Author explicit line breaks or enlarge the shape; do not shrink unreadably.")


def _rect(item):
    return (item["x"], item["y"], item["x"] + item["width"], item["y"] + item["height"])


def _intersect(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.1 and min(a[3], b[3]) - max(a[1], b[1]) > 0.1


def segment_hits_rect(a, b, rect):
    """Liang-Barsky clipping against the rectangle interior, including diagonal lanes."""
    x0, y0, x1, y1 = rect
    x0, y0, x1, y1 = x0 + 0.1, y0 + 0.1, x1 - 0.1, y1 - 0.1
    dx, dy = b[0] - a[0], b[1] - a[1]
    lower, upper = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]),
                 (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        elif p < 0:
            lower = max(lower, q / p)
        else:
            upper = min(upper, q / p)
        if lower > upper:
            return False
    return lower <= upper


def _port(value, where):
    _object(value, {"side", "position"}, where)
    if not isinstance(value.get("side"), str) or value["side"] not in SIDES:
        raise ValueError(f"{where}: declare side as north/east/south/west")
    position = _number(value.get("position", 0.5), f"{where}.position")
    if not 0 < position < 1:
        raise ValueError(f"{where}.position: must be strictly between 0 and 1")
    return {"side": value["side"], "position": position}


def _port_point(node, port):
    side, t = port["side"], port["position"]
    x, y, w, h = node["x"], node["y"], node["width"], node["height"]
    # One coordinate unit outside the rectangle; rendered attached connectors use
    # the actual shape perimeter. This bound is intentionally conservative.
    return {"north": (x + t * w, y - 1), "south": (x + t * w, y + h + 1),
            "east": (x + w + 1, y + t * h), "west": (x - 1, y + t * h)}[side]


def route_edge(edge, nodes):
    source, target = nodes[edge["source"]], nodes[edge["target"]]
    dx = target["x"] + target["width"] / 2 - source["x"] - source["width"] / 2
    dy = target["y"] + target["height"] / 2 - source["y"] - source["height"] / 2
    vertical = abs(dy) >= abs(dx)
    default_source = ("south" if dy >= 0 else "north") if vertical else ("east" if dx >= 0 else "west")
    opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}
    sp = edge.get("source_port", {"side": default_source, "position": 0.5})
    tp = edge.get("target_port", {"side": opposite[default_source], "position": 0.5})
    start, end = _port_point(source, sp), _port_point(target, tp)
    if "waypoints" in edge:
        middle = [(p["x"], p["y"]) for p in edge["waypoints"]]
    elif abs(start[0] - end[0]) < 0.1 or abs(start[1] - end[1]) < 0.1:
        middle = []
    elif vertical:
        my = (start[1] + end[1]) / 2
        middle = [(start[0], my), (end[0], my)]
    else:
        mx = (start[0] + end[0]) / 2
        middle = [(mx, start[1]), (mx, end[1])]
    points = [start, *middle, end]
    # Remove exact adjacent duplicates without removing authored nontrivial bends.
    points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    return {"source_port": sp, "target_port": tp, "points": points}


def _point_along(points, fraction):
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    remaining = sum(lengths) * fraction
    for a, b, length in zip(points, points[1:], lengths):
        if remaining <= length and length:
            ratio = remaining / length
            return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
        remaining -= length
    return points[-1]


def prepare(spec):
    """Validate semantics, geometry, type/field contracts and modeled label lanes."""
    spec = copy.deepcopy(spec)
    _object(spec, TOP_FIELDS, "manifest")
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("Use flowchart schema_version 1")
    for key in ("title", "claim", "source_note"):
        _text(spec.get(key), key)
    if spec.get("data_kind") != "schematic":
        raise ValueError("Flowcharts require data_kind='schematic'; they are not empirical charts")
    for key in ("nodes", "edges", "groups"):
        if key == "groups":
            spec.setdefault(key, [])
        if not isinstance(spec.get(key), list):
            raise ValueError(f"{key}: expected an array")
    if not spec["nodes"]:
        raise ValueError("At least one node is required")
    style = spec.setdefault("style", {})
    _object(style, STYLE_FIELDS, "style")
    defaults = {"font_family": "Microsoft YaHei", "font_size": 18,
                "publication_width_mm": 160, "minimum_font_pt": 8.5,
                "maximum_height_mm": 225, "minimum_dpi": 300}
    for key, value in defaults.items():
        style.setdefault(key, value)
    _text(style["font_family"], "style.font_family")
    if any(char in style["font_family"] for char in ";=\n\r"):
        raise ValueError("font_family cannot contain style delimiters")
    for key in set(STYLE_FIELDS) - {"font_family"}:
        _number(style[key], f"style.{key}", positive=True)
    canvas = spec.setdefault("canvas", {})
    _object(canvas, {"width", "height"}, "canvas")
    all_ids = set()
    for collection, allowed in (("nodes", NODE_FIELDS), ("edges", EDGE_FIELDS), ("groups", GROUP_FIELDS)):
        for item in spec[collection]:
            _object(item, allowed, collection)
            ident = item.get("id")
            if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", ident):
                raise ValueError(f"{collection}: id must use a stable letter-led ASCII identifier")
            if ident in all_ids or ident.startswith("mm-layer-"):
                raise ValueError(f"Duplicate or reserved id: {ident}")
            all_ids.add(ident)
            if "source_ref" in item:
                _text(item["source_ref"], f"{ident}.source_ref")
            if collection != "edges":
                _geometry(item, ident)
                _text(item.get("label"), f"{ident}.label")
    nodes = {node["id"]: node for node in spec["nodes"]}
    groups = {group["id"]: group for group in spec["groups"]}
    size = style["font_size"]
    for node in nodes.values():
        kind = node.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError(f"{node['id']}: unsupported node kind")
        if kind == "decision":
            _text(node.get("condition_label"), f"{node['id']}.condition_label")
        elif "condition_label" in node:
            raise ValueError(f"{node['id']}: condition_label is only valid for decisions")
        if "group" in node:
            if not isinstance(node["group"], str) or node["group"] not in groups:
                raise ValueError(f"{node['id']}: unknown group")
            group = groups[node["group"]]
            if (node["x"] < group["x"] + 8 or node["y"] < group["y"] + size + 14
                    or node["x"] + node["width"] > group["x"] + group["width"] - 8
                    or node["y"] + node["height"] > group["y"] + group["height"] - 8):
                raise ValueError(f"{node['id']}: node exceeds group bounds or covers its heading")
        factor = 0.60 if kind == "decision" else (0.78 if kind in {"input", "output"} else 1)
        _text_budget(node_text(node), node["width"] * factor - 16,
                     node["height"] * (0.55 if kind == "decision" else 1) - 12,
                     size, node["id"])
    group_title_bounds = {}
    for group in groups.values():
        _text_budget(group["label"], group["width"] - 24, size + 4, size, group["id"])
        group_title_bounds[group["id"]] = (group["x"] + 12, group["y"] + 5,
            group["x"] + 12 + text_width(group["label"], size), group["y"] + 5 + size + 3)
    physical_objects = [*nodes.values(), *groups.values()]
    for key, axis in (("width", "x"), ("height", "y")):
        canvas.setdefault(key, max(item[axis] + item[key] for item in physical_objects) + 20)
        _number(canvas[key], f"canvas.{key}", positive=True)
    for item in physical_objects:
        if item["x"] + item["width"] > canvas["width"] or item["y"] + item["height"] > canvas["height"]:
            raise ValueError(f"{item['id']}: exceeds declared canvas")
    for i, node in enumerate(spec["nodes"]):
        for other in spec["nodes"][i + 1:]:
            if _intersect(_rect(node), _rect(other)):
                raise ValueError(f"Node overlap: {node['id']} / {other['id']}")
    for i, group in enumerate(spec["groups"]):
        for other in spec["groups"][i + 1:]:
            if _intersect(_rect(group), _rect(other)):
                raise ValueError(f"Background groups overlap: {group['id']} / {other['id']}")
    outgoing = {node: [] for node in nodes}
    routes, label_bounds = {}, {}
    for edge in spec["edges"]:
        ident = edge["id"]
        if not isinstance(edge.get("source"), str) or edge["source"] not in nodes:
            raise ValueError(f"{ident}: missing source endpoint")
        if not isinstance(edge.get("target"), str) or edge["target"] not in nodes:
            raise ValueError(f"{ident}: missing target endpoint")
        outgoing[edge["source"]].append(edge)
        edge.setdefault("relation", "process")
        if not isinstance(edge["relation"], str) or edge["relation"] not in RELATIONS:
            raise ValueError(f"{ident}: unsupported relation")
        if "label" in edge:
            _text(edge["label"], f"{ident}.label")
        if "waypoints" in edge:
            if not isinstance(edge["waypoints"], list):
                raise ValueError(f"{ident}.waypoints: expected an array")
            for point in edge["waypoints"]:
                _object(point, {"x", "y"}, f"{ident}.waypoints")
                for key in ("x", "y"):
                    _number(point.get(key), f"{ident}.waypoint.{key}")
        if edge["relation"] in {"loop", "feedback"} or edge["source"] == edge["target"]:
            if len(edge.get("waypoints", [])) < 2:
                raise ValueError(f"{ident}: loop/feedback needs at least two explicit lane waypoints")
        for key in ("source_port", "target_port"):
            if key in edge:
                edge[key] = _port(edge[key], f"{ident}.{key}")
        if "label_position" in edge:
            position = _number(edge["label_position"], f"{ident}.label_position")
            if not 0 <= position <= 1:
                raise ValueError(f"{ident}.label_position: must be between 0 and 1")
        if "label_offset" in edge:
            _object(edge["label_offset"], {"x", "y"}, f"{ident}.label_offset")
            for key in ("x", "y"):
                value = edge["label_offset"].get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{ident}.label_offset.{key}: finite number required")
        route = route_edge(edge, nodes)
        routes[ident] = route
        for x, y in route["points"]:
            if not 0 <= x <= canvas["width"] or not 0 <= y <= canvas["height"]:
                raise ValueError(f"{ident}: connector lane exceeds canvas")
        for node in nodes.values():
            if any(segment_hits_rect(a, b, _rect(node)) for a, b in zip(route["points"], route["points"][1:])):
                related = node["id"] in {edge["source"], edge["target"]}
                description = "its endpoint shape" if related else "unrelated node"
                raise ValueError(f"{ident}: connector crosses {description} {node['id']}; author another lane")
        for group_id, bounds in group_title_bounds.items():
            if any(segment_hits_rect(a, b, bounds) for a, b in zip(route["points"], route["points"][1:])):
                raise ValueError(f"{ident}: connector covers group heading {group_id}; reserve a clear entry lane")
        if "label" in edge:
            anchor = _point_along(route["points"], edge.get("label_position", 0.5))
            offset = edge.get("label_offset", {"x": 0, "y": -14})
            cx, cy = anchor[0] + offset["x"], anchor[1] + offset["y"]
            width = max(text_width(line, size) for line in edge["label"].split("\n")) + 8
            height = len(edge["label"].split("\n")) * (size + 3)
            bounds = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > canvas["width"] or bounds[3] > canvas["height"]:
                raise ValueError(f"{ident}: branch label exceeds canvas; set label_position/label_offset")
            for node in nodes.values():
                if _intersect(bounds, _rect(node)):
                    raise ValueError(f"{ident}: branch label covers node {node['id']}; set label_position/label_offset")
            for other_id, other in label_bounds.items():
                if _intersect(bounds, other):
                    raise ValueError(f"{ident}: branch label overlaps {other_id}")
            for group_id, heading in group_title_bounds.items():
                if _intersect(bounds, heading):
                    raise ValueError(f"{ident}: branch label covers group heading {group_id}")
            for group in groups.values():
                gx0, gy0, gx1, gy1 = _rect(group)
                corners = [(gx0, gy0), (gx1, gy0), (gx1, gy1), (gx0, gy1), (gx0, gy0)]
                if any(segment_hits_rect(a, b, bounds) for a, b in zip(corners, corners[1:])):
                    raise ValueError(f"{ident}: branch label crosses group border {group['id']}; reserve a label lane")
            label_bounds[ident] = bounds
    for node in nodes.values():
        if node["kind"] == "decision":
            branches = outgoing[node["id"]]
            labels = [edge.get("label", "").strip().casefold() for edge in branches]
            if len(branches) < 2 or not all(labels) or len(set(labels)) != len(labels):
                raise ValueError(f"{node['id']}: decision requires at least two distinctly labeled branches")
    effective_pt = size * style["publication_width_mm"] / canvas["width"] * 72 / 25.4
    if effective_pt < style["minimum_font_pt"]:
        raise ValueError(f"Font becomes {effective_pt:.2f} pt at {style['publication_width_mm']} mm; "
                         f"minimum is {style['minimum_font_pt']} pt. Enlarge or split the figure.")
    warnings = []
    physical_height = canvas["height"] / canvas["width"] * style["publication_width_mm"]
    if physical_height > style["maximum_height_mm"]:
        warnings.append("Figure exceeds declared publication height; split it or choose an explicit page slot.")
    return spec, {"routes": routes, "label_bounds": label_bounds,
                  "group_heading_bounds": group_title_bounds,
                  "effective_font_pt_at_publication_width": round(effective_pt, 3),
                  "figure_height_mm": round(physical_height, 3), "warnings": warnings}


def _num(value):
    return f"{value:g}"


def make_drawio(spec, preflight):
    canvas, font = spec["canvas"], spec["style"]
    root = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "mathmodel-flowchart",
                                 "version": "24.7.17"})
    diagram = ET.SubElement(root, "diagram", {"id": "mathmodel-schematic", "name": spec["title"]})
    model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": _num(canvas["width"]), "dy": _num(canvas["height"]), "grid": "1", "gridSize": "10",
        "guides": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": _num(canvas["width"]), "pageHeight": _num(canvas["height"]),
        "math": "0", "shadow": "0", "background": "#FFFFFF"})
    cells = ET.SubElement(model, "root")
    ET.SubElement(cells, "mxCell", {"id": "0"})
    # Layers and ordering keep group regions behind lines and native node text.
    for ident, name in (("mm-layer-background", "分组背景"), ("mm-layer-connectors", "语义连线"),
                        ("mm-layer-nodes", "节点与文字")):
        ET.SubElement(cells, "mxCell", {"id": ident, "value": name, "parent": "0"})
    common = (f"html=0;whiteSpace=wrap;fontFamily={font['font_family']};fontSize={_num(font['font_size'])};"
              "fontColor=#202A35;align=center;verticalAlign=middle;strokeWidth=1.25;spacing=6;")
    for group in spec["groups"]:
        cell = ET.SubElement(cells, "mxCell", {"id": group["id"], "value": group["label"],
            "style": common + "rounded=0;fillColor=none;strokeColor=#9C8AB2;dashed=1;dashPattern=4 4;"
                                  "align=left;verticalAlign=top;spacingLeft=12;spacingTop=5;fontColor=#6C5489;",
            "vertex": "1", "parent": "mm-layer-background"})
        ET.SubElement(cell, "mxGeometry", {**{k: _num(group[k]) for k in ("x", "y", "width", "height")}, "as": "geometry"})
    for edge in spec["edges"]:
        route = preflight["routes"][edge["id"]]
        ports = []
        for name, port in (("exit", route["source_port"]), ("entry", route["target_port"])):
            px, py = SIDES[port["side"]]
            if port["side"] in {"north", "south"}:
                px = port["position"]
            else:
                py = port["position"]
            ports.append(f"{name}X={_num(px)};{name}Y={_num(py)};{name}Perimeter=1;")
        color = "#896745" if edge["relation"] in {"feedback", "loop"} else "#42617A"
        arrow = "none" if edge["relation"] == "association" else "block"
        # Edge labels have no authored box width; using node wrapping here makes
        # draw.io break Chinese branch names into a vertical character stack.
        edge_common = common.replace("whiteSpace=wrap;", "whiteSpace=nowrap;")
        style = (edge_common + "edgeStyle=none;rounded=0;" + "".join(ports) +
                 f"strokeColor={color};endArrow={arrow};endFill=1;endSize=7;labelBackgroundColor=#FFFFFF;")
        if edge["relation"] == "association":
            style += "dashed=1;dashPattern=3 3;"
        cell = ET.SubElement(cells, "mxCell", {"id": edge["id"], "value": edge.get("label", ""),
            "style": style, "edge": "1", "parent": "mm-layer-connectors", "source": edge["source"],
            "target": edge["target"], "relation": edge["relation"]})
        geometry = ET.SubElement(cell, "mxGeometry", {
            "relative": "1", "x": _num(2 * edge.get("label_position", 0.5) - 1), "y": "0", "as": "geometry"})
        if len(route["points"]) > 2:
            waypoints = ET.SubElement(geometry, "Array", {"as": "points"})
            for x, y in route["points"][1:-1]:
                ET.SubElement(waypoints, "mxPoint", {"x": _num(x), "y": _num(y)})
        if "label" in edge:
            offset = edge.get("label_offset", {"x": 0, "y": -14})
            ET.SubElement(geometry, "mxPoint", {"x": _num(offset["x"]), "y": _num(offset["y"]), "as": "offset"})
    shape_styles = {
        "input": "shape=parallelogram;perimeter=parallelogramPerimeter;fillColor=#FBECDD;strokeColor=#A88966;",
        "output": "shape=parallelogram;perimeter=parallelogramPerimeter;fillColor=#FBECDD;strokeColor=#A88966;",
        "process": "rounded=1;arcSize=8;fillColor=#ECF4FA;strokeColor=#688098;",
        "decision": "shape=rhombus;perimeter=rhombusPerimeter;fillColor=#E3F2F0;strokeColor=#739B98;",
        "start": "rounded=1;arcSize=50;fillColor=#EEF1F4;strokeColor=#8594A0;",
        "end": "rounded=1;arcSize=50;fillColor=#EEF1F4;strokeColor=#8594A0;",
        "annotation": "text;strokeColor=none;fillColor=none;align=left;",
    }
    for node in spec["nodes"]:
        attrs = {"id": node["id"], "value": node_text(node), "style": common + shape_styles[node["kind"]],
                 "vertex": "1", "parent": "mm-layer-nodes", "kind": node["kind"]}
        if "group" in node:
            attrs["groupRef"] = node["group"]
        cell = ET.SubElement(cells, "mxCell", attrs)
        ET.SubElement(cell, "mxGeometry", {**{k: _num(node[k]) for k in ("x", "y", "width", "height")}, "as": "geometry"})
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _svg_report(path):
    data = path.read_text(encoding="utf-8-sig")
    root = ET.fromstring(data)
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("Renderer did not write SVG")
    reasons = []
    if any(node.tag.rsplit("}", 1)[-1] == "foreignObject" for node in root.iter()):
        reasons.append("foreignObject/HTML labels are not a portable Typst SVG input")
    if re.search(r"\b(?:light-dark|var)\s*\(", data):
        reasons.append("Dynamic CSS colors need target-renderer verification")
    if "Text is not SVG - cannot display" in data:
        reasons.append("Renderer SVG contains a text fallback warning")
    return {"known_typst_hazards": reasons,
            "universal_direct_embedding_supported": False,
            "typst_asset": "figure.png", "latex_asset": "figure.pdf",
            "next_step": "Inspect the final target-PDF at the declared size; SVG export alone does not prove compatibility."}


def _inspect_exports(output, publication_width_mm):
    png = output / "figure.png"
    data = png.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        raise ValueError("Renderer did not write a valid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        raise ValueError("Renderer PNG is empty")
    pdf = output / "figure.pdf"
    if not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Renderer did not write a PDF")
    inspection = {"png_width_px": width, "png_height_px": height,
                  "png_dpi_at_publication_width": round(width / publication_width_mm * 25.4, 2),
                  "actual_figure_height_mm_at_publication_width": round(height / width * publication_width_mm, 3),
                  "pdf_vector_check": "unverified (PyMuPDF unavailable)",
                  "svg_compatibility": _svg_report(output / "figure.svg")}
    try:
        import pymupdf
    except ImportError:
        pass
    else:
        with pymupdf.open(pdf) as document:
            drawings = sum(len(page.get_drawings()) for page in document)
            images = sum(len(page.get_images(full=True)) for page in document)
            if len(document) != 1 or not drawings or images:
                raise ValueError("Expected one vector PDF page with native drawings and no raster images")
            inspection.update({"pdf_pages": len(document), "pdf_vector_paths": drawings,
                               "pdf_raster_images": images, "pdf_vector_check": "passed",
                               "observed_pdf_fonts": sorted({font[3] for page in document for font in page.get_fonts()})})
    return inspection


def render(manifest, output, *, drawio=None, scale=3.0, timeout=90):
    manifest, output = Path(manifest).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise ValueError("Output must be a NEW directory; existing artifacts are never overwritten")
    scale = _number(scale, "PNG scale", positive=True)
    if scale < 3:
        raise ValueError("PNG scale must be at least 3 for manuscript inspection")
    spec, preflight = prepare(read_manifest(manifest))
    if drawio is not None:
        drawio = Path(drawio).resolve(strict=True)
        if not drawio.is_file():
            raise ValueError("--drawio requires a known executable file")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "figure.drawio"
    source.write_bytes(make_drawio(spec, preflight))
    (output / "figure_contract.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"schema_version": 1, "renderer": "draw.io native shapes/lines", "adapter_version": VERSION,
              "title": spec["title"], "claim": spec["claim"], "source_note": spec["source_note"],
              "manifest_sha256": _sha(manifest), "data_kind": "schematic", "preflight": preflight,
              "status": "source_only", "visual_review": "pending",
              "scientific_validation": "not established by this drawing or source declaration",
              "execution_evidence": "none; an algorithm diagram does not prove a solver was run",
              "layout_mode": "explicit authored coordinates and lanes; no automatic smart layout",
              "editability": "native text, shapes and attached connectors on three editable layers",
              "grouping": "background regions with groupRef membership; not move-together native containers",
              "route_scope": "conservative rectangle/label model; edge crossings, actual perimeters and typography still require visual review",
              "manuscript_assets": {"typst": "figure.png (only after renderer export)",
                                    "latex": "figure.pdf (only after renderer export)"},
              "warnings": list(preflight["warnings"]), "artifacts": {}, "exports": []}
    failure = None
    if drawio is None:
        report["warnings"].append("No renderer selected: PNG/PDF/SVG and target visual review remain pending.")
    else:
        try:
            for fmt in ("png", "pdf", "svg"):
                destination = output / f"figure.{fmt}"
                command = [str(drawio), "--export", "--format", fmt, "--output", str(destination)]
                command += (["--scale", _num(scale), "--border", "12"] if fmt == "png" else ["--crop"] if fmt == "pdf" else [])
                command.append(str(source))
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
                receipt = {"format": fmt, "returncode": result.returncode,
                           "output_written": destination.exists() and destination.stat().st_size > 0}
                report["exports"].append(receipt)
                if result.returncode or not receipt["output_written"]:
                    raise RuntimeError(f"draw.io {fmt} export failed; exit={result.returncode}")
            report["inspection"] = _inspect_exports(output, spec["style"]["publication_width_mm"])
            dpi = report["inspection"]["png_dpi_at_publication_width"]
            if dpi < spec["style"]["minimum_dpi"]:
                raise ValueError(f"PNG is {dpi} dpi at the declared width; increase --scale")
            actual_height = report["inspection"]["actual_figure_height_mm_at_publication_width"]
            if actual_height > spec["style"]["maximum_height_mm"]:
                report["warnings"].append("Renderer-cropped output exceeds publication height; split it or select a taller slot.")
            report["status"] = "exported"
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, ET.ParseError) as exc:
            failure = str(exc)
            report.update({"status": "export_failed", "error": failure})
    for artifact in output.iterdir():
        if artifact.is_file():
            report["artifacts"][artifact.name] = {"sha256": _sha(artifact), "bytes": artifact.stat().st_size}
    report_path = output / "rendering_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if failure:
        raise RuntimeError(f"{failure}; preserved source and report at {output}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Explicit v1 schematic JSON contract")
    parser.add_argument("--output", required=True, type=Path, help="NEW directory; never overwrite existing output")
    parser.add_argument("--drawio", type=Path, help="Known draw.io executable; omit to produce source only")
    parser.add_argument("--scale", type=float, default=3, help="PNG renderer scale, at least 3 (default 3)")
    args = parser.parse_args()
    try:
        report = render(args.manifest, args.output, drawio=args.drawio, scale=args.scale)
    except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "visual_review": report["visual_review"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
