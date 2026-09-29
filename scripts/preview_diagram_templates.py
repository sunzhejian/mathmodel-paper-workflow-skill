"""Build a local comparison sheet from the four pinned diagram-template previews."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ("roadmap-5band", "framework-3col", "stageflow-3col", "taskflow-land")


def build(skill_root: Path, output: Path) -> Path:
    skill_root = skill_root.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    source = skill_root / "vendor/sci-box/skills/scibox-diagram/assets"
    previews = [source / name / "preview.png" for name in TEMPLATES]
    if any(not path.is_file() for path in previews):
        missing = [str(path) for path in previews if not path.is_file()]
        raise FileNotFoundError(f"Diagram previews are missing: {missing}")
    card_w, card_h, pad = 700, 560, 24
    canvas = Image.new("RGB", (card_w * 2 + pad * 3, card_h * 2 + pad * 3), "#edf1f4")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 21)
    except OSError:
        font = ImageFont.load_default(size=21)
    for index, (name, path) in enumerate(zip(TEMPLATES, previews)):
        left = pad + (index % 2) * (card_w + pad)
        top = pad + (index // 2) * (card_h + pad)
        draw.rounded_rectangle((left, top, left + card_w, top + card_h),
                               radius=12, fill="#ffffff", outline="#b9c4cf", width=2)
        draw.text((left + 20, top + 13), name, fill="#263e5e", font=font)
        with Image.open(path) as original:
            picture = original.convert("RGB")
            picture.thumbnail((card_w - 40, card_h - 75), Image.Resampling.LANCZOS)
        x = left + (card_w - picture.width) // 2
        y = top + 56 + (card_h - 75 - picture.height) // 2
        canvas.paste(picture, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New local PNG output path")
    parser.add_argument("--skill-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = build(args.skill_root, args.output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
