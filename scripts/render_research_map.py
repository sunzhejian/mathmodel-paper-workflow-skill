"""Read declared-CRS study geometries, or preserve a verified official China map."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

OFFICIAL_HOSTS = {"bzdt.ch.mnr.gov.cn", "bzdt.mnr.gov.cn"}


def official_basemap(manifest):
    """Verify source bytes against the official HTTPS download, never redraw borders."""
    source = Path(manifest)
    meta = json.loads(source.read_text(encoding="utf-8"))
    url = meta["source_url"]
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in OFFICIAL_HOSTS:
        raise ValueError("China basemap must come from the official standard-map service")
    if not meta.get("review_number") or not meta.get("sha256"):
        raise ValueError("Official review number and source SHA-256 are required")
    raw = (source.parent / meta["file"]).read_bytes()
    if len(raw) > 20*1024*1024 or hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        raise ValueError("Basemap hash or size differs")
    with urlopen(url, timeout=30) as response:
        if urlparse(response.url).hostname not in OFFICIAL_HOSTS:
            raise ValueError("Official source redirected outside the approved service")
        downloaded = response.read(20*1024*1024+1)
    if hashlib.sha256(downloaded).hexdigest() != meta["sha256"]:
        raise ValueError("Local basemap does not match the official download")
    return raw, meta


def load_features(source, declared_crs=None, encoding=None):
    from pyproj import CRS
    from shapely.geometry import shape
    path = Path(source)
    if path.suffix.lower() == ".shp":
        import shapefile
        peers = {p.suffix.lower(): p for p in path.parent.iterdir()
                 if p.stem.lower() == path.stem.lower()}
        if not all(s in peers for s in (".shp", ".shx", ".dbf", ".prj")):
            raise ValueError("Shapefile requires matching .shp/.shx/.dbf/.prj files")
        crs = CRS.from_wkt(peers[".prj"].read_text(encoding="utf-8-sig"))
        if declared_crs and not crs.equals(CRS.from_user_input(declared_crs)):
            raise ValueError("Declared CRS conflicts with the Shapefile .prj")
        with shapefile.Reader(shp=str(peers[".shp"]), shx=str(peers[".shx"]),
                              dbf=str(peers[".dbf"]), encoding=encoding or (peers[".cpg"].read_text().strip() if ".cpg" in peers else "utf-8")) as reader:
            features = [(shape(r.shape.__geo_interface__), r.record.as_dict()) for r in reader.iterShapeRecords()]
        files = [peers[s] for s in (".shp", ".shx", ".dbf", ".prj", ".cpg") if s in peers]
    elif path.suffix.lower() in (".json", ".geojson"):
        if not declared_crs:
            raise ValueError("Declare GeoJSON CRS explicitly; RFC 7946 uses EPSG:4326")
        crs = CRS.from_user_input(declared_crs)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError("Expected a GeoJSON FeatureCollection")
        features = [(shape(f["geometry"]), f.get("properties", {})) for f in data["features"]]
        files = [path]
    else:
        raise ValueError("Use a Shapefile or GeoJSON FeatureCollection")
    if not features or len(features) > 100000 or any(g.is_empty or not g.is_valid for g, _ in features):
        raise ValueError("Empty, invalid or excessive geometries; do not silently repair boundaries")
    return features, crs, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def render(source, output, crs=None, target_crs=None, field=None, official=None, font=None, encoding=None):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    if font:
        from matplotlib import font_manager
        font_manager.fontManager.addfont(font)
        matplotlib.rcParams['font.family'] = font_manager.FontProperties(fname=font).get_name()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    if official:
        from PIL import Image
        raw, meta = official_basemap(official)
        image = Image.open(io.BytesIO(raw))
        ax.imshow(image, interpolation="none")
        ax.axis("off")
        fig.text(.5, .02, meta["review_number"]+" | "+meta["source_url"], ha="center", fontsize=7)
        receipt = dict(mode="official_basemap_preserved", basemap_sha256=meta["sha256"],
                       source_url=meta["source_url"], review_number=meta["review_number"],
                       border_redrawn=False, image_cropped=False, publication_review_required=True)
    else:
        import numpy as np
        from pyproj import CRS, Transformer
        from shapely.ops import transform
        from shapely.geometry.polygon import orient
        from matplotlib.path import Path as PlotPath
        from matplotlib.patches import PathPatch
        features, input_crs, hashes = load_features(source, crs, encoding)
        geographic = Transformer.from_crs(input_crs, "EPSG:4326", always_xy=True)
        bounds = np.array([transform(geographic.transform, g).bounds for g, _ in features])
        if not np.isfinite(bounds).all():
            raise ValueError('CRS transform produced non-finite coordinates')
        xmin, ymin = bounds[:, :2].min(axis=0)
        xmax, ymax = bounds[:, 2:].max(axis=0)
        # A broad China-containing extent must use the unmodified official-map branch.
        if xmin < 140 and xmax > 70 and ymin < 56 and ymax > 3 and (xmax-xmin > 4 or ymax-ymin > 4):
            raise ValueError("China regional/national or world extent requires a verified official basemap; arbitrary national borders are not exported")
        projected = CRS.from_user_input(target_crs) if target_crs else input_crs
        transformer = Transformer.from_crs(input_crs, projected, always_xy=True)
        values = [float(props[field]) for _, props in features] if field else [0]*len(features)
        if not np.isfinite(values).all():
            raise ValueError("Map values must be finite, with no missing join keys")
        norm = matplotlib.colors.Normalize(min(values), max(values) if max(values) != min(values) else min(values)+1)
        for (original, props), value in zip(features, values):
            geom = transform(transformer.transform, original)
            parts = list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
            for part in parts:
                color = plt.cm.Blues(.55 if min(values) == max(values) else norm(value))
                if part.geom_type == "Polygon":
                    part = orient(part, sign=1)
                    paths = []
                    for ring in [part.exterior, *part.interiors]:
                        vertices = np.asarray(ring.coords)
                        codes = [PlotPath.MOVETO]+[PlotPath.LINETO]*(len(vertices)-2)+[PlotPath.CLOSEPOLY]
                        paths.append(PlotPath(vertices, codes))
                    ax.add_patch(PathPatch(PlotPath.make_compound_path(*paths), facecolor=color, edgecolor="#263545", linewidth=.7))
                elif part.geom_type == "LineString":
                    ax.plot(*part.xy, color="#264e6b", linewidth=1)
                elif part.geom_type == "Point":
                    ax.scatter([part.x], [part.y], color="#265b79", s=20)
                else:
                    raise ValueError("Unsupported geometry: "+part.geom_type)
        ax.autoscale()
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel(projected.to_string())
        ax.set_title("Research geometry · "+(field or "study area"))
        if field and min(values) != max(values):
            fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="Blues"), ax=ax, label=field)
        if field and min(values) == max(values):
            ax.text(.02, .98, f"{field} = {values[0]:g}", transform=ax.transAxes, va="top")
        fig.tight_layout()
        receipt = dict(mode="study_geometry", source_hashes=hashes, feature_count=len(features),
                       input_crs=input_crs.to_string(), output_crs=projected.to_string(),
                       field=field, boundary_source_verified=False, publication_review_required=True)
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(output.with_suffix("."+suffix), dpi=240)
    plt.close(fig)
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path)
    p.add_argument("--crs")
    p.add_argument("--target-crs")
    p.add_argument("--field")
    p.add_argument("--font")
    p.add_argument("--encoding")
    p.add_argument("--official-manifest", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if bool(args.input) == bool(args.official_manifest):
        p.error("Choose either a study dataset or a verified official basemap manifest")
    print(json.dumps(render(args.input, args.output, args.crs, args.target_crs, args.field, args.official_manifest, args.font, args.encoding), ensure_ascii=False))
