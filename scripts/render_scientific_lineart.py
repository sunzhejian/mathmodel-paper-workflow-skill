"""Render editable scientific line art from a JSON scene; no raster tracing."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def control_volume():
    items = []
    def add(kind, **kw):
        items.append(dict(type=kind, id=f"object-{len(items)+1}", **kw))
    def text(x, y, value, size=10):
        add("text", p=[x, y], text=value, size=size)
    def line(a, b, **kw):
        add("line", a=a, b=b, **kw)
    def arrow(a, b, **kw):
        add("arrow", a=a, b=b, **kw)
    # r is the mid-radius, making dV = 2*pi*r*dr*dz exact for this annulus.
    add("annulus", p=[29, 26], radius=15, thickness=3, hatch="////")
    line([9, 26], [49, 26], dashed=True)
    line([29, 6], [29, 46], dashed=True)
    arrow([29, 26], [29+13.5/math.sqrt(2), 26+13.5/math.sqrt(2)])
    text(28, 29, "$O$")
    text(36, 29, "$r$")
    arrow([48, 11], [48, 14], double=True)
    line([29, 11], [50, 11])
    line([29, 14], [50, 14])
    text(53, 13, "$dr$")
    text(40, 43, "轴向厚度 $dz$")
    text(30, 51, "$dV=2\\pi r\\,dr\\,dz$")
    text(30, 58, "(a) 环带控制体")
    add("rect", p=[96, 19], width=22, height=13)
    line([67, 19], [149, 19])
    line([67, 32], [149, 32])
    line([76, 18], [76, 34], dashed=True)
    line([140, 18], [140, 34], dashed=True)
    arrow([79, 26], [95, 26])
    arrow([119, 26], [137, 26])
    text(80, 13, "内侧流入")
    text(134, 13, "外侧流出")
    text(107, 15, "$x_i$")
    text(107, 25, "$C_i, T_i$")
    text(96, 37, "$x_{i-1/2}$")
    text(118, 37, "$x_{i+1/2}$")
    arrow([97, 43], [117, 43], double=True)
    text(107, 49, "控制体宽度")
    text(107, 57, "(b) 累积率 = 流入率 - 流出率")
    for start, label, side in [(10, "中心对称边界", "center"),
                                (87, "表面对流边界", "surface")]:
        line([start, 71], [start+61, 71])
        xs = [start+2, start+23, start+44]
        if side == "center":
            add("rect", p=[xs[0], 68], width=10.5, height=6, hatch="////")
            line([xs[0]+10.5, 66], [xs[0]+10.5, 79], dashed=True)
            text(xs[0], 65, "$x_0$")
            text(xs[1], 65, "$x_1$")
            text(xs[2], 65, "$x_2$")
            text(start+31, 92, "$x_0=0,\\quad F_{-1/2}=0$")
            ends = [xs[0], xs[0]+10.5]
        else:
            add("rect", p=[xs[2]-10.5, 68], width=10.5, height=6, hatch="////")
            line([xs[2]-10.5, 66], [xs[2]-10.5, 79], dashed=True)
            text(xs[0], 65, "$x_{N-2}$")
            text(xs[1], 65, "$x_{N-1}$")
            text(xs[2], 65, "$x_N$")
            text(start+30, 92, "$-D C_n=\\beta(C_s-C_a^{eff})$", 9)
            ends = [xs[2]-10.5, xs[2]]
        for x in xs:
            add("circle", p=[x, 71], radius=.4, fill="black")
        text(start+31, 78, label)
        arrow([ends[0], 82], [ends[1], 82], double=True)
        text(sum(ends)/2, 87, "$\\Delta x/2$", 8)
    text(80, 101, "(c) 均匀网格的中心与表面半控制体")
    return dict(width_mm=160, height_mm=105, items=items,
                scientific_scope="机制示意，非实验结果；边界通量向外为正，r 为环带中线半径")


def render(scene, output, font=None):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Circle, Rectangle, Wedge
    from matplotlib.font_manager import FontProperties
    width, height = scene["width_mm"], scene["height_mm"]
    if not all(isinstance(n, (int, float)) and math.isfinite(n) and 20 <= n <= 1000
               for n in [width, height]) or not 1 <= len(scene["items"]) <= 500:
        raise ValueError("Invalid scene extent or object count")
    props = FontProperties(fname=font) if font else None
    matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42,
                               "text.usetex": False, "mathtext.fontset": "stix",
                               "hatch.linewidth": .35})
    fig = plt.figure(figsize=(width/25.4, height/25.4))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, width), ylim=(height, 0), aspect="equal")
    ax.axis("off")
    ids = set()
    for item in scene["items"]:
        ident, kind = item["id"], item["type"]
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", ident) or ident in ids:
            raise ValueError("Object ids must be unique")
        ids.add(ident)
        for key in ("p", "a", "b"):
            if key in item:
                point = item[key]
                if len(point) != 2 or not all(isinstance(n, (int, float)) and math.isfinite(n) and 0 <= n <= bound for n, bound in zip(point, [width, height])):
                    raise ValueError("Coordinates must be finite and inside the canvas")
        if kind == "text" and (not isinstance(item.get("text"), str) or len(item["text"]) > 500 or not 5 <= item.get("size", 10) <= 36):
            raise ValueError("Invalid label or font size")
        lw = float(item.get("line_width", .65))
        if not .15 <= lw <= 3:
            raise ValueError("Line width must be 0.15–3 pt")
        style = dict(edgecolor="black", facecolor=item.get("fill", "none"), linewidth=lw,
                     hatch=item.get("hatch"), gid=ident)
        if kind in ("circle", "annulus"):
            radius = float(item["radius"])
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("Invalid radius")
            if kind == "circle":
                patch = Circle(item["p"], radius, **style)
            else:
                thickness = float(item["thickness"])
                if not 0 < thickness < radius:
                    raise ValueError("Annulus thickness must be inside its radius")
                patch = Wedge(item["p"], radius, 0, 360, width=thickness, **style)
            ax.add_patch(patch)
        elif kind == "rect":
            if min(item["width"], item["height"]) <= 0:
                raise ValueError("Invalid rectangle")
            ax.add_patch(Rectangle(item["p"], item["width"], item["height"], **style))
        elif kind == "line":
            ax.plot([item["a"][0], item["b"][0]], [item["a"][1], item["b"][1]],
                    color="black", linewidth=lw, linestyle="--" if item.get("dashed") else "-", gid=ident)
        elif kind == "arrow":
            ax.annotate("", xy=item["b"], xytext=item["a"],
                        arrowprops=dict(arrowstyle="<->" if item.get("double") else "->",
                                        color="black", linewidth=lw, shrinkA=0, shrinkB=0), gid=ident)
        elif kind == "text":
            ax.text(*item["p"], item["text"], fontsize=item.get("size", 10),
                    ha=item.get("align", "center"), va="center", color="black", fontproperties=props, gid=ident)
        else:
            raise ValueError("Unsupported primitive: " + kind)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(output.with_suffix("."+suffix), dpi=300, facecolor="white")
    plt.close(fig)
    output.with_suffix(".scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    svg = output.with_suffix(".svg").read_bytes()
    if b"<image" in svg:
        raise ValueError("Line art unexpectedly contains a raster image")
    receipt = {"scope": scene.get("scientific_scope", "scientific schematic"),
               "editable_scene": output.with_suffix(".scene.json").name,
               "svg_sha256": hashlib.sha256(svg).hexdigest(), "object_count": len(ids),
               "raster_elements": 0, "scientific_result_verified": False}
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, help="Editable JSON scene (defaults to control-volume schematic)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", help="CJK font file for Chinese labels")
    args = parser.parse_args()
    source = json.loads(args.spec.read_text(encoding="utf-8")) if args.spec else control_volume()
    print(json.dumps(render(source, args.output, args.font), ensure_ascii=False))
