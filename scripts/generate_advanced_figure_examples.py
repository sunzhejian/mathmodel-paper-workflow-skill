"""Freeze synthetic CSV examples and render data-bound scientific figures."""
from __future__ import annotations
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_scientific_data", ROOT / "scripts/render_scientific_data.py")
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)


def inputs(folder: Path) -> list[Path]:
    if folder.exists():
        raise ValueError("Use a new synthetic input directory")
    folder.mkdir(parents=True)
    rng = np.random.default_rng(20261002)
    a = rng.normal(size=180)
    b = .7 * a + rng.normal(scale=.8, size=180)
    c = -.65 * a + rng.normal(scale=.6, size=180)
    d = .25 * b + rng.normal(scale=1.1, size=180)
    feature_rows = np.column_stack((a, b, c, d)).tolist()
    prediction_rows = []
    for split, count in (("train", 140), ("test", 70)):
        actual = rng.gamma(3, 8, count)
        for model, scale in (("示例方案 A", 3.2), ("示例方案 B", 2.0)):
            pred = actual + rng.normal(scale=scale * (1.35 if split == "test" else 1), size=count)
            prediction_rows.extend((model, split, f"{split}-{i:03}", float(t), float(p)) for i, (t, p) in enumerate(zip(actual, pred)))
    grid_rows = [(float(x), float(y), float(.3 + .6 * (x - .6) ** 2 + .35 * (y - .3) ** 2 + .03 * np.sin(8 * x)))
                 for y in np.linspace(0, 1, 10) for x in np.linspace(0, 1, 9)]
    contracts = {
        "correlation": ({"template_id": "correlation-pairgrid", "title": "多变量关系与分布", "data": "features.csv",
                         "columns": [{"key": key, "label": label, "unit": "1"} for key, label in zip("abcd", ("变量 A", "变量 B", "变量 C", "变量 D"))]},
                        list("abcd"), feature_rows),
        "prediction": ({"template_id": "prediction-marginal-grid", "title": "预测与参考值：分布及误差", "data": "predictions.csv", "unit": "1",
                        "roles": {key: key for key in ("model", "split", "sample_id", "actual", "predicted")}, "comparison": True},
                       ["model", "split", "sample_id", "actual", "predicted"], prediction_rows),
        "surface": ({"template_id": "rf-tpe-surface", "title": "参数网格与响应曲面", "data": "response-grid.csv",
                     **{key: {"key": key, "label": label, "unit": "1"} for key, label in zip("xyz", ("参数 X", "参数 Y", "响应 Z"))}},
                    list("xyz"), grid_rows),
    }
    paths = []
    for name, (contract, headings, rows) in contracts.items():
        contract.update(schema_version=1, data_kind="synthetic", source_note="Deterministic synthetic illustration; no model training, optimizer or competition evidence.")
        with (folder / contract["data"]).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headings)
            writer.writerows(rows)
        path = folder / (name + ".json")
        path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New synthetic demo directory")
    parser.add_argument("--font", type=Path, required=True, help="Existing CJK font file")
    args = parser.parse_args(argv)
    try:
        args.font.resolve(strict=True)
        if args.output.exists():
            raise ValueError("Use a new demo directory")
        paths = inputs(args.output / "inputs")
        for path in paths:
            report = RENDER.render(path, args.output / path.stem, args.font)
            print(json.dumps({"case": path.stem, "data_kind": report["data_kind"], "statistics": report["statistics"]}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
