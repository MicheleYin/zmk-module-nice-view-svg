"""Convert PNG/SVG assets into LVGL I1/I2 bitmaps for XML codegen/preview."""

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


def pack_i2_pixels(pixels: list[int], width: int, height: int) -> bytes:
    stride = (width + 3) // 4
    packed = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            pixel = pixels[y * width + x]
            packed[y * stride + x // 4] |= pixel << (6 - 2 * (x % 4))
    return bytes(packed)


def pack_i1_png(data: bytes) -> tuple[int, int, bytes]:
    (width, height), pixels = monochrome_pixels_from_png(data)
    return width, height, pack_i1_pixels(pixels, width, height)


def pack_i2_png(
    data: bytes, bounds: tuple[int, int, int, int] | None = None
) -> tuple[int, int, bytes]:
    """Pack RGBA PNG to I2 (0=transparent, 1=fg, 2=bg). Optional crop bounds."""
    Image = _load_pillow()
    with Image.open(BytesIO(data)) as source:
        rgba = source.convert("RGBA")
        if bounds is not None:
            x, y, width, height = bounds
            rgba = rgba.crop((x, y, x + width, y + height))
        else:
            width, height = rgba.size
        pixels = []
        for red, green, blue, alpha in rgba.getdata():
            if alpha < 128:
                pixels.append(0)
            elif red + green + blue < 3 * 128:
                pixels.append(1)
            else:
                pixels.append(2)
        return width, height, pack_i2_pixels(pixels, width, height)


def rasterize_svg_file(
    path: Path, width: int | None = None, height: int | None = None
) -> bytes:
    rasterizer = shutil.which("rsvg-convert")
    if not rasterizer:
        raise RuntimeError("SVG assets require rsvg-convert on PATH")
    command = [rasterizer, "--format=png"]
    if width is not None:
        command.append(f"--width={width}")
    if height is not None:
        command.append(f"--height={height}")
    command.append(str(path))
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="replace") or "rsvg-convert failed"
        )
    return result.stdout


def load_png_or_svg_bytes(
    path: Path, width: int | None = None, height: int | None = None
) -> bytes:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return rasterize_svg_file(path, width, height)
    if suffix in {".png", ".bmp", ".gif"}:
        data = path.read_bytes()
        if width is None and height is None:
            return data
        Image = _load_pillow()
        with Image.open(BytesIO(data)) as image:
            rgba = image.convert("RGBA")
            if width is not None and height is not None:
                rgba = rgba.resize((width, height))
            elif width is not None:
                ratio = width / rgba.width
                rgba = rgba.resize((width, max(1, int(rgba.height * ratio))))
            elif height is not None:
                ratio = height / rgba.height
                rgba = rgba.resize((max(1, int(rgba.width * ratio)), height))
            output = BytesIO()
            rgba.save(output, format="PNG")
            return output.getvalue()
    raise ValueError(f"unsupported image type: {path.suffix}")


def load_i1_image(
    path: Path, width: int | None = None, height: int | None = None
) -> tuple[int, int, bytes]:
    return pack_i1_png(load_png_or_svg_bytes(path, width, height))


def load_i2_image(
    path: Path, width: int | None = None, height: int | None = None
) -> tuple[int, int, bytes]:
    return pack_i2_png(load_png_or_svg_bytes(path, width, height))


def load_i1_png(path: Path) -> tuple[int, int, bytes]:
    return load_i1_image(path)


def preview_rgba_image(
    path: Path, width: int | None = None, height: int | None = None
):
    """Return a Pillow RGBA image for host preview compositing."""
    Image = _load_pillow()
    data = load_png_or_svg_bytes(path, width, height)
    return Image.open(BytesIO(data)).convert("RGBA")


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
