"""Convert PNG/SVG assets into LVGL I1/I2 bitmaps for XML codegen/preview."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

DITHER_ALGORITHMS = ("none", "floyd-steinberg", "atkinson", "bayer")
BAYER_MATRIX = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
ERROR_DIFFUSION_NEIGHBORS = {
    "floyd-steinberg": (
        (1, 0, 7 / 16),
        (-1, 1, 3 / 16),
        (0, 1, 5 / 16),
        (1, 1, 1 / 16),
    ),
    "atkinson": (
        (1, 0, 1 / 8),
        (2, 0, 1 / 8),
        (-1, 1, 1 / 8),
        (0, 1, 1 / 8),
        (1, 1, 1 / 8),
        (0, 2, 1 / 8),
    ),
}


def _load_pillow():
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "PNG assets require Pillow; run with uv and tools/requirements.txt"
        ) from error
    return Image


def _hard_threshold_luma(value: int, threshold: int = 128) -> int:
    """Map grayscale to binary without dithering (0=black/fg, 1=white/bg)."""
    return 0 if value < threshold else 1


def _ordered_dither(
    values: list[float], width: int, height: int, alpha: bytes | None
) -> list[int]:
    pixels = [1] * len(values)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if alpha is not None and alpha[index] < 128:
                continue
            threshold = 128 + (BAYER_MATRIX[y % 4][x % 4] - 7.5) * 16
            pixels[index] = 0 if values[index] < threshold else 1
    return pixels


def _diffuse_error(
    values: list[float],
    x: int,
    y: int,
    width: int,
    height: int,
    error: float,
    neighbors: tuple[tuple[int, int, float], ...],
    alpha: bytes | None,
) -> None:
    for dx, dy, weight in neighbors:
        next_x, next_y = x + dx, y + dy
        if not (0 <= next_x < width and 0 <= next_y < height):
            continue
        next_index = next_y * width + next_x
        if alpha is None or alpha[next_index] >= 128:
            values[next_index] += error * weight


def _error_diffuse(
    grayscale: bytes,
    width: int,
    height: int,
    dither: str,
    alpha: bytes | None,
) -> list[int]:
    values = [float(value) for value in grayscale]
    pixels = [1] * len(values)
    neighbors = ERROR_DIFFUSION_NEIGHBORS[dither]
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if alpha is not None and alpha[index] < 128:
                continue
            old_value = values[index]
            new_value = 0 if old_value < 128 else 255
            pixels[index] = 0 if new_value == 0 else 1
            _diffuse_error(
                values,
                x,
                y,
                width,
                height,
                old_value - new_value,
                neighbors,
                alpha,
            )
    return pixels


def _monochrome_values(
    grayscale: bytes,
    width: int,
    height: int,
    dither: str,
    alpha: bytes | None = None,
) -> list[int]:
    if dither not in DITHER_ALGORITHMS:
        raise ValueError(
            f"unknown dithering algorithm '{dither}'; choose from "
            f"{', '.join(DITHER_ALGORITHMS)}"
        )
    if dither == "bayer":
        return _ordered_dither(
            [float(value) for value in grayscale], width, height, alpha
        )
    if dither in ERROR_DIFFUSION_NEIGHBORS:
        return _error_diffuse(grayscale, width, height, dither, alpha)
    return [_hard_threshold_luma(value) for value in grayscale]


def monochrome_pixels_from_rgba(
    image, dither: str = "none", preserve_transparency: bool = False
) -> tuple[tuple[int, int], list[int]]:
    image_module = _load_pillow()
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha = bytes(rgba.getchannel("A").tobytes()) if preserve_transparency else None
    if preserve_transparency:
        grayscale = rgba.convert("L").tobytes()
    else:
        background = image_module.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        grayscale = background.convert("L").tobytes()
    pixels = _monochrome_values(grayscale, width, height, dither, alpha)
    return (width, height), pixels


def monochrome_pixels_from_png(
    data: bytes, dither: str = "none"
) -> tuple[tuple[int, int], list[int]]:
    Image = _load_pillow()
    with Image.open(BytesIO(data)) as source:
        return monochrome_pixels_from_rgba(source, dither)


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


def pack_i1_png(data: bytes, dither: str = "none") -> tuple[int, int, bytes]:
    (width, height), pixels = monochrome_pixels_from_png(data, dither)
    return width, height, pack_i1_pixels(pixels, width, height)


def _gif_output_size(
    source_size: tuple[int, int], width: int | None, height: int | None
) -> tuple[int, int]:
    source_width, source_height = source_size
    if width is not None and height is not None:
        return width, height
    if width is not None:
        return width, max(1, int(source_height * width / source_width))
    if height is not None:
        return max(1, int(source_width * height / source_height)), height
    return source_size


def _gif_frame_bitmap(
    rgba, output_size, preserve_transparency: bool, dither: str
) -> bytes:
    if preserve_transparency:
        (_, _), monochrome = monochrome_pixels_from_rgba(
            rgba, dither, preserve_transparency=True
        )
        alpha = rgba.getchannel("A").tobytes()
        pixels = [
            0 if alpha[index] < 128 else (1 if pixel == 0 else 2)
            for index, pixel in enumerate(monochrome)
        ]
        return pack_i2_pixels(pixels, *output_size)

    (_, _), pixels = monochrome_pixels_from_rgba(rgba, dither)
    return pack_i1_pixels(pixels, *output_size)


def _gif_play_count(loop_count: int | None) -> int:
    if loop_count is None:
        return 1
    if loop_count == 0:
        return 0
    return loop_count + 1


def _load_gif_frames(
    path: Path,
    width: int | None,
    height: int | None,
    preserve_transparency: bool,
    dither: str,
) -> tuple[int, int, list[tuple[bytes, int]], int]:
    image_module = _load_pillow()
    frames: list[tuple[bytes, int]] = []
    with image_module.open(path) as source:
        if source.format != "GIF":
            raise ValueError(f"animated image must be a GIF: {path}")
        play_count = _gif_play_count(source.info.get("loop"))
        output_size = _gif_output_size(source.size, width, height)

        for frame_index in range(source.n_frames):
            source.seek(frame_index)
            rgba = source.convert("RGBA")
            if rgba.size != output_size:
                rgba = rgba.resize(
                    output_size, resample=image_module.Resampling.NEAREST
                )
            duration_ms = max(20, min(int(source.info.get("duration") or 100), 60000))
            bitmap = _gif_frame_bitmap(
                rgba, output_size, preserve_transparency, dither
            )
            frames.append((bitmap, duration_ms))

    return output_size[0], output_size[1], frames, play_count


def load_i1_gif_frames(
    path: Path,
    width: int | None = None,
    height: int | None = None,
    dither: str = "none",
) -> tuple[int, int, list[tuple[bytes, int]], int]:
    return _load_gif_frames(path, width, height, False, dither)


def load_i2_gif_frames(
    path: Path,
    width: int | None = None,
    height: int | None = None,
    dither: str = "none",
) -> tuple[int, int, list[tuple[bytes, int]], int]:
    return _load_gif_frames(path, width, height, True, dither)


def pack_i2_png(
    data: bytes,
    bounds: tuple[int, int, int, int] | None = None,
    dither: str = "none",
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
        (_, _), monochrome = monochrome_pixels_from_rgba(
            rgba, dither, preserve_transparency=True
        )
        alpha = rgba.getchannel("A").tobytes()
        pixels = [
            0 if alpha[index] < 128 else (1 if pixel == 0 else 2)
            for index, pixel in enumerate(monochrome)
        ]
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
    if suffix in {".png", ".bmp", ".gif", ".webp"}:
        data = path.read_bytes()
        if width is None and height is None:
            return data
        Image = _load_pillow()
        with Image.open(BytesIO(data)) as image:
            rgba = image.convert("RGBA")
            # Nearest-neighbor only — bilinear resize creates gray edge fringes.
            resample = Image.Resampling.NEAREST
            if width is not None and height is not None:
                rgba = rgba.resize((width, height), resample=resample)
            elif width is not None:
                ratio = width / rgba.width
                rgba = rgba.resize(
                    (width, max(1, int(rgba.height * ratio))), resample=resample
                )
            elif height is not None:
                ratio = height / rgba.height
                rgba = rgba.resize(
                    (max(1, int(rgba.width * ratio)), height), resample=resample
                )
            output = BytesIO()
            rgba.save(output, format="PNG")
            return output.getvalue()
    raise ValueError(f"unsupported image type: {path.suffix}")


def load_i1_image(
    path: Path,
    width: int | None = None,
    height: int | None = None,
    dither: str = "none",
) -> tuple[int, int, bytes]:
    return pack_i1_png(load_png_or_svg_bytes(path, width, height), dither)


def load_i2_image(
    path: Path,
    width: int | None = None,
    height: int | None = None,
    dither: str = "none",
) -> tuple[int, int, bytes]:
    return pack_i2_png(load_png_or_svg_bytes(path, width, height), dither=dither)


def load_i1_png(path: Path) -> tuple[int, int, bytes]:
    return load_i1_image(path)


def preview_rgba_image(
    path: Path,
    width: int | None = None,
    height: int | None = None,
    dither: str = "none",
):
    """Return a Pillow RGBA image for host preview compositing."""
    Image = _load_pillow()
    data = load_png_or_svg_bytes(path, width, height)
    with Image.open(BytesIO(data)) as source:
        rgba = source.convert("RGBA")
    if dither == "none":
        return rgba
    (_, _), monochrome = monochrome_pixels_from_rgba(
        rgba, dither, preserve_transparency=True
    )
    alpha = rgba.getchannel("A").tobytes()
    output = bytearray()
    for index, pixel in enumerate(monochrome):
        value = 0 if pixel == 0 else 255
        output.extend((value, value, value, alpha[index]))
    return Image.frombytes("RGBA", rgba.size, bytes(output))


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
        is_svg_text = element.tag.rsplit("}", 1)[-1] == "text"
        if not is_svg_text and not is_dynamic(element):
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
                result.stderr.decode("utf-8", errors="replace") or "rsvg-convert failed"
            )
        Image = _load_pillow()
        with Image.open(BytesIO(result.stdout)) as image:
            # Dither=NONE: convert("1") otherwise Floyd–Steinberg speckles edges.
            mono = image.convert("1", dither=Image.Dither.NONE)
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
