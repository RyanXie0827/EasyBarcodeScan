#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


ICNS_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def normalize_source_image(source_path: Path, output_size: int = 1024) -> Image.Image:
    with Image.open(source_path) as source_image:
        prepared = source_image.convert("RGBA")
        contained = ImageOps.contain(prepared, (output_size, output_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
        offset_x = (output_size - contained.width) // 2
        offset_y = (output_size - contained.height) // 2
        canvas.alpha_composite(contained, (offset_x, offset_y))
        return canvas


def build_icon_assets(source_path: Path, output_dir: Path, asset_name: str) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_image = normalize_source_image(source_path)

    normalized_png_path = output_dir / f"{asset_name}_1024.png"
    icns_path = output_dir / f"{asset_name}.icns"
    ico_path = output_dir / f"{asset_name}.ico"

    normalized_image.save(normalized_png_path, format="PNG")
    normalized_image.save(icns_path, format="ICNS", sizes=ICNS_SIZES)
    normalized_image.save(ico_path, format="ICO", sizes=ICO_SIZES)

    return normalized_png_path, icns_path, ico_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build macOS/Windows icon assets from a square PNG or any raster image.")
    parser.add_argument(
        "--source",
        default="assets/icons/app_icon_1024.png",
        help="source image path; non-square images will be centered onto a transparent 1024x1024 canvas",
    )
    parser.add_argument("--output-dir", default="assets/icons", help="directory for generated icon assets")
    parser.add_argument("--name", default="app_icon", help="base file name for generated assets")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"图标源文件不存在：{source_path}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    normalized_png_path, icns_path, ico_path = build_icon_assets(source_path, output_dir, args.name)

    print(f"PNG : {normalized_png_path}")
    print(f"ICNS: {icns_path}")
    print(f"ICO : {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
