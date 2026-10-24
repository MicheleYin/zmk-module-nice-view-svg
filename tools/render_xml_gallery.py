"""Render paired PNG previews for the XML screen and widget gallery."""

from __future__ import annotations

import argparse
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__:
    from tools.nice_view_xml_assets import (
        DITHER_ALGORITHMS,
        monochrome_pixels_from_rgba,
    )
    from tools.nice_view_xml import load_catalog
    from tools.nice_view_xml_components import expand_screen_file
    from tools.nice_view_xml_live import build_preview_config
    from tools.nice_view_xml_preview import preview_png, preview_xml_text
else:
    from nice_view_xml_assets import (
        DITHER_ALGORITHMS,
        monochrome_pixels_from_rgba,
    )
    from nice_view_xml import load_catalog
    from nice_view_xml_components import expand_screen_file
    from nice_view_xml_live import build_preview_config
    from nice_view_xml_preview import preview_png, preview_xml_text

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "docs" / "ui" / "screens"
SAMPLES = ROOT / "docs" / "ui" / "samples"
DEFAULT_OUTPUT = ROOT / "docs" / "ui" / "gallery"
WASM_RENDERER = ROOT / "build" / "lvgl_wasm" / "web" / "preview.js"

PAIRS = (
    (
        "nice-view",
        SCREENS / "nice-view-left.xml",
        SCREENS / "nice-view-right.xml",
    ),
    (
        "oled",
        SCREENS / "oled-left.xml",
        SCREENS / "oled-right.xml",
    ),
)


def render_pair(
    name: str,
    left: Path,
    right: Path,
    output_dir: Path,
    dither_override: str | None = None,
) -> None:
    fields = load_catalog(ROOT / "tools" / "status_fields.json")
    for side, screen, role in (
        ("left", left, "central"),
        ("right", right, "peripheral"),
    ):
        config = build_preview_config(screen, role)
        xml_text = expand_screen_file(screen)
        rendered_xml = preview_xml_text(xml_text, fields, config["values"][role], role)
        preview_png(
            rendered_xml, output_dir / f"{name}-{side}.png", screen, dither_override
        )
        render_animation_sheets(
            xml_text, screen, output_dir, f"{name}-{side}", dither_override
        )


def render_sample(
    screen: Path, output_dir: Path, dither_override: str | None = None
) -> None:
    fields = load_catalog(ROOT / "tools" / "status_fields.json")
    config = build_preview_config(screen, "central")
    xml_text = expand_screen_file(screen)
    rendered_xml = preview_xml_text(
        xml_text, fields, config["values"]["central"], "central"
    )
    prefix = f"sample-{screen.stem}"
    preview_png(
        rendered_xml, output_dir / f"{prefix}.png", screen, dither_override
    )
    render_animation_sheets(
        xml_text, screen, output_dir, prefix, dither_override
    )
    render_animated_screen_gif(
        rendered_xml, screen, output_dir, prefix, dither_override
    )


def _monochrome_gif_frames(image, dither: str):
    from PIL import Image

    frames = []
    durations = []
    for frame_index in range(image.n_frames):
        image.seek(frame_index)
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        (width, height), pixels = monochrome_pixels_from_rgba(background, dither)
        frame = Image.new("1", (width, height))
        frame.putdata([0 if pixel == 0 else 255 for pixel in pixels])
        frames.append(frame)
        durations.append(int(image.info.get("duration") or 100))
    return frames, durations


def _write_animation_sheet(frames, durations, output_path: Path) -> None:
    from PIL import Image, ImageDraw

    columns = min(8, len(frames))
    rows = math.ceil(len(frames) / columns)
    cell_width = max(frame.width for frame in frames)
    cell_height = max(frame.height for frame in frames) + 14
    sheet = Image.new("1", (columns * cell_width, rows * cell_height), 1)
    draw = ImageDraw.Draw(sheet)
    for frame_index, (frame, duration) in enumerate(zip(frames, durations)):
        x = (frame_index % columns) * cell_width
        y = (frame_index // columns) * cell_height
        draw.text((x + 2, y + 2), f"{frame_index}: {duration}ms", fill=0)
        sheet.paste(frame, (x, y + 14))
    sheet.save(output_path, format="PNG")


def render_animation_sheets(
    xml_text: str,
    screen_path: Path,
    output_dir: Path,
    prefix: str,
    dither_override: str | None = None,
) -> list[Path]:
    from PIL import Image

    output_paths = []
    root = ET.fromstring(xml_text)
    for element in root.iter("lv_image"):
        source = element.get("src", "")
        source_path = (screen_path.parent / source).resolve()
        if source_path.suffix.lower() != ".gif" or not source_path.is_file():
            continue

        with Image.open(source_path) as image:
            if image.format != "GIF" or image.n_frames < 2:
                continue
            dither = dither_override or element.get("dither", "none")
            frames, durations = _monochrome_gif_frames(image, dither)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{prefix}-animation-{len(output_paths)}.png"
        _write_animation_sheet(frames, durations, output_path)
        output_paths.append(output_path)
    return output_paths


def render_animated_screen_gif(
    rendered_xml: str,
    screen_path: Path,
    output_dir: Path,
    prefix: str,
    dither_override: str | None = None,
) -> Path | None:
    from PIL import Image

    root = ET.fromstring(rendered_xml)
    animated_images = [
        element
        for element in root.iter("lv_image")
        if Path(element.get("src", "")).suffix.lower() == ".gif"
    ]
    if len(animated_images) != 1:
        return None

    image_element = animated_images[0]
    source_path = (screen_path.parent / image_element.get("src", "")).resolve()
    if not source_path.is_file():
        return None
    dither = dither_override or image_element.get("dither", "none")
    frames = []
    durations = []

    with tempfile.TemporaryDirectory(prefix="zmk-screen-gif-") as temp_dir:
        temp_path = Path(temp_dir)
        with Image.open(source_path) as source:
            if source.format != "GIF" or source.n_frames < 2:
                return None
            repeat_count = source.info.get("loop", 0)
            for frame_index in range(source.n_frames):
                source.seek(frame_index)
                duration = max(20, min(int(source.info.get("duration") or 100), 60000))
                asset_path = temp_path / f"frame-{frame_index}.png"
                source.convert("RGBA").save(asset_path)

                frame_root = ET.fromstring(rendered_xml)
                frame_image = next(
                    element
                    for element in frame_root.iter("lv_image")
                    if element.get("src") == image_element.get("src")
                )
                frame_image.set("src", str(asset_path))
                frame_image.set("dither", dither)
                preview_path = temp_path / f"screen-{frame_index}.png"
                preview_png(
                    ET.tostring(frame_root, encoding="unicode"),
                    preview_path,
                    screen_path,
                    dither,
                )
                with Image.open(preview_path) as preview:
                    frames.append(preview.convert("1").copy())
                durations.append(duration)

    if not frames:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{prefix}.gif"
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=repeat_count,
        disposal=2,
        optimize=True,
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dither", choices=DITHER_ALGORITHMS)
    arguments = parser.parse_args()
    if not WASM_RENDERER.is_file():
        parser.error(
            "build the LVGL renderer first with emcmake cmake -S tools/lvgl_wasm "
            "-B build/lvgl_wasm && cmake --build build/lvgl_wasm"
        )
    for name, left, right in PAIRS:
        render_pair(name, left, right, arguments.output_dir, arguments.dither)
    for sample in sorted(SAMPLES.glob("nice-view-*.xml")):
        render_sample(sample, arguments.output_dir, arguments.dither)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
