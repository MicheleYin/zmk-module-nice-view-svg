"""Convert PNG backgrounds into LVGL I1 bitmaps for XML codegen/preview."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path


def _load_pillow():
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "PNG assets require Pillow; run with uv and tools/requirements.txt"
        ) from error
    return Image


def monochrome_pixels_from_png(data: bytes) -> tuple[tuple[int, int], list[int]]:
    Image = _load_pillow()
    with Image.open(BytesIO(data)) as source:
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        grayscale = background.convert("L")
        pixels = [0 if value < 128 else 1 for value in grayscale.getdata()]
        return grayscale.size, pixels


def pack_i1_pixels(pixels: list[int], width: int, height: int) -> bytes:
    stride = (width + 7) // 8
    packed = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            if pixels[y * width + x] == 0:
                packed[y * stride + x // 8] |= 1 << (7 - (x % 8))
    return bytes(packed)


def pack_i1_png(data: bytes) -> tuple[int, int, bytes]:
    (width, height), pixels = monochrome_pixels_from_png(data)
    return width, height, pack_i1_pixels(pixels, width, height)


def load_i1_png(path: Path) -> tuple[int, int, bytes]:
    return pack_i1_png(path.read_bytes())


def export_static_svg_background(svg_path: Path, png_path: Path) -> Path:
    """Rasterize an SVG with dynamic bindings removed into a 1-bit PNG."""
    rasterizer = shutil.which("rsvg-convert")
    if not rasterizer:
        raise RuntimeError("exporting SVG backgrounds requires rsvg-convert")

    root = ET.fromstring(svg_path.read_text())
    parents = {child: parent for parent in root.iter() for child in parent}

    def is_dynamic(element: ET.Element) -> bool:
        return any(
            element.get(attr) is not None
            for attr in (
                "data-nvp-bind",
                "data-nvp-render",
                "data-nvp-when",
                "data-nvp-slot",
            )
        )

    for element in list(root.iter()):
        if not is_dynamic(element):
            continue
        parent = parents.get(element)
        if parent is None:
            continue
        parent.remove(element)

    svg_text = ET.tostring(root, encoding="unicode")
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as handle:
        handle.write(svg_text)
        temp_svg = Path(handle.name)
    try:
        result = subprocess.run(
            [
                rasterizer,
                "--format=png",
                f"--width={_view_width(root)}",
                f"--height={_view_height(root)}",
                str(temp_svg),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.decode("utf-8", errors="replace")
                or "rsvg-convert failed"
            )
        Image = _load_pillow()
        with Image.open(BytesIO(result.stdout)) as image:
            mono = image.convert("1")
            png_path.parent.mkdir(parents=True, exist_ok=True)
            mono.save(png_path, format="PNG")
    finally:
        temp_svg.unlink(missing_ok=True)
    return png_path


def _view_width(root: ET.Element) -> int:
    view_box = root.get("viewBox", "").replace(",", " ").split()
    if len(view_box) == 4:
        return int(float(view_box[2]))
    return int(float(root.get("width", "160")))


def _view_height(root: ET.Element) -> int:
    view_box = root.get("viewBox", "").replace(",", " ").split()
    if len(view_box) == 4:
        return int(float(view_box[3]))
    return int(float(root.get("height", "68")))
