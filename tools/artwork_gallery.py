"""Build screen-sized artwork assets and dither previews from docs/ui/artwork."""

from __future__ import annotations

import argparse
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

if __package__:
    from tools.nice_view_xml_codegen import MAX_ANIMATION_BYTES, MAX_ANIMATION_FRAMES
    from tools.nice_view_xml_assets import DITHER_ALGORITHMS, monochrome_pixels_from_rgba
else:
    from nice_view_xml_codegen import MAX_ANIMATION_BYTES, MAX_ANIMATION_FRAMES
    from nice_view_xml_assets import DITHER_ALGORITHMS, monochrome_pixels_from_rgba

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs" / "ui" / "artwork"
ASSET_OUTPUT = ROOT / "docs" / "ui" / "assets" / "artwork"
SAMPLE_OUTPUT = ROOT / "docs" / "ui" / "samples"
PREVIEW_OUTPUT = ROOT / "docs" / "ui" / "gallery" / "artwork"
README = ROOT / "README.md"
START_MARKER = "<!-- ARTWORK GALLERY START -->"
END_MARKER = "<!-- ARTWORK GALLERY END -->"
COUNTERCLOCKWISE_ROTATIONS = {"blossom-meadow.jpeg": 90}
SUPPORTED_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def _slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _read_frames(path: Path, size: tuple[int, int]):
    frames = []
    durations = []
    with Image.open(path) as source:
        frame_count = getattr(source, "n_frames", 1)
        loop = int(source.info.get("loop", 0))
        for frame_index in range(frame_count):
            source.seek(frame_index)
            frame = ImageOps.exif_transpose(source.convert("RGBA"))
            rotation = COUNTERCLOCKWISE_ROTATIONS.get(path.name, 0)
            if rotation:
                frame = frame.rotate(rotation, expand=True)
            frames.append(
                ImageOps.fit(
                    frame,
                    size,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
            )
            durations.append(
                max(20, min(int(source.info.get("duration") or 100), 60000))
            )
    return frames, durations, loop


def _dither(frame: Image.Image, algorithm: str) -> Image.Image:
    (width, height), pixels = monochrome_pixels_from_rgba(frame, algorithm)
    result = Image.new("1", (width, height))
    result.putdata([0 if pixel == 0 else 255 for pixel in pixels])
    return result


def _save_gif(
    frames: list[Image.Image], durations: list[int], loop: int, path: Path
) -> None:
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=loop,
        disposal=2,
        optimize=True,
    )


def _limit_screen_frames(
    frames: list[Image.Image], durations: list[int], loop: int
) -> tuple[list[Image.Image], list[int], int]:
    width, height = frames[0].size
    bytes_per_frame = ((width + 7) // 8) * height
    frame_limit = min(MAX_ANIMATION_FRAMES, MAX_ANIMATION_BYTES // bytes_per_frame)
    if len(frames) <= frame_limit:
        return frames, durations, loop

    limited_frames = []
    limited_durations = []
    for index in range(frame_limit):
        start = index * len(frames) // frame_limit
        end = (index + 1) * len(frames) // frame_limit
        limited_frames.append(frames[start])
        limited_durations.append(sum(durations[start:end]))
    return limited_frames, limited_durations, loop


def _repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _save_preview_set(
    slug: str,
    frames: list[Image.Image],
    durations: list[int],
    loop: int,
    size: tuple[int, int],
) -> dict[str, Path]:
    output_dir = PREVIEW_OUTPUT / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = {}
    first_frames = []
    for algorithm in DITHER_ALGORITHMS:
        converted = [_dither(frame, algorithm) for frame in frames]
        suffix = ".gif" if len(converted) > 1 else ".png"
        output_path = output_dir / f"{algorithm}{suffix}"
        if suffix == ".gif":
            _save_gif(converted, durations, loop, output_path)
        else:
            converted[0].save(output_path, format="PNG", optimize=True)
        variants[algorithm] = output_path
        first_frames.append(converted[0])

    width, height = size
    sheet = Image.new("1", (width * len(DITHER_ALGORITHMS), height + 14), 1)
    draw = ImageDraw.Draw(sheet)
    for index, (algorithm, frame) in enumerate(zip(DITHER_ALGORITHMS, first_frames)):
        x = index * width
        draw.text((x + 2, 2), algorithm, fill=0)
        sheet.paste(frame, (x, 14))
    comparison_path = output_dir / "comparison.png"
    sheet.save(comparison_path, format="PNG", optimize=True)
    variants["comparison"] = comparison_path
    return variants


def _write_screen_sample(slug: str, asset_name: str) -> Path:
    sample_path = SAMPLE_OUTPUT / f"nice-view-artwork-{slug}.xml"
    SAMPLE_OUTPUT.mkdir(parents=True, exist_ok=True)
    root = ET.Element("component")
    view = ET.SubElement(
        root,
        "view",
        {
            "extends": "lv_obj",
            "width": "160",
            "height": "68",
            "style_bg_color": "0xffffff",
            "style_pad_all": "0",
            "scrollable": "false",
        },
    )
    ET.SubElement(
        view,
        "lv_image",
        {
            "src": f"../assets/artwork/{asset_name}",
            "x": "0",
            "y": "0",
            "width": "160",
            "height": "68",
            "dither": "none",
        },
    )
    ET.SubElement(
        view,
        "zmk_status_text",
        {
            "field": "layer.index",
            "x": "158",
            "y": "60",
            "font_size": "8",
            "anchor": "end",
        },
    )
    sample_path.write_text(
        "<!-- Generated by tools/artwork_gallery.py; edit the source artwork instead. -->\n"
        + ET.tostring(root, encoding="unicode")
        + "\n",
        encoding="utf-8",
    )
    return sample_path


def _update_readme(records: list[dict[str, object]]) -> None:
    text = README.read_text(encoding="utf-8")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER, start + len(START_MARKER))
    if start < 0 or end < 0:
        raise ValueError(f"README.md must contain {START_MARKER} and {END_MARKER}")

    lines = [
        START_MARKER,
        "## Artwork Dither Gallery",
        "",
        "Put raster artwork in `docs/ui/artwork/`, then run:",
        "",
        "```sh",
        "uv run --isolated --with-requirements tools/requirements.txt python tools/artwork_gallery.py",
        "```",
        "",
        "Each comparison is cropped to the 160×68 Nice!View screen and shows the available conversion modes left to right: none, Floyd–Steinberg, Atkinson, and Bayer. The links open the individual PNG or animated GIF output and the generated XML screen sample.",
        "",
        "| Artwork | Dither comparison | Screen sample | Individual modes |",
        "| --- | --- | --- | --- |",
    ]
    for record in records:
        source = html.escape(str(record["source"]))
        variants = record["variants"]
        assert isinstance(variants, dict)
        comparison = _repo_path(variants["comparison"])
        sample = str(record["sample"])
        mode_links = " · ".join(
            f"[{html.escape(mode)}]({_repo_path(variants[mode])})"
            for mode in DITHER_ALGORITHMS
        )
        lines.append(
            f'| [{source}](docs/ui/artwork/{source}) '
            f'| <img src="{comparison}" alt="{source}: all dithering modes" width="640"> '
            f'| [Screen XML]({sample}) '
            f"| {mode_links} |"
        )
    lines.extend([END_MARKER, ""])
    replacement = "\n".join(lines)
    README.write_text(
        text[:start] + replacement + text[end + len(END_MARKER) :], encoding="utf-8"
    )


def _remove_stale_samples(active_slugs: set[str]) -> None:
    generated_marker = (
        "<!-- Generated by tools/artwork_gallery.py; edit the source artwork instead. -->"
    )
    for sample_path in SAMPLE_OUTPUT.glob("nice-view-artwork-*.xml"):
        slug = sample_path.stem.removeprefix("nice-view-artwork-")
        if slug not in active_slugs and sample_path.read_text(encoding="utf-8").startswith(
            generated_marker
        ):
            sample_path.unlink()


def build_gallery(input_dir: Path, size: tuple[int, int]) -> int:
    sources = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not sources:
        raise ValueError(f"no supported images found in {input_dir}")

    records = []
    used_slugs = set()
    for source_path in sources:
        slug = _slug(source_path.stem)
        if not slug or slug in used_slugs:
            raise ValueError(
                f"image names must have unique, non-empty slugs: {source_path.name}"
            )
        used_slugs.add(slug)

        frames, durations, loop = _read_frames(source_path, size)
        screen_frames, screen_durations, screen_loop = _limit_screen_frames(
            frames, durations, loop
        )
        asset_suffix = ".gif" if len(screen_frames) > 1 else ".png"
        asset_path = ASSET_OUTPUT / f"{slug}{asset_suffix}"
        ASSET_OUTPUT.mkdir(parents=True, exist_ok=True)
        if asset_suffix == ".gif":
            _save_gif(screen_frames, screen_durations, screen_loop, asset_path)
        else:
            screen_frames[0].save(asset_path, format="PNG", optimize=True)

        variants = _save_preview_set(slug, frames, durations, loop, size)
        sample_path = _write_screen_sample(slug, asset_path.name)
        records.append(
            {
                "source": source_path.name,
                "variants": variants,
                "sample": sample_path.relative_to(ROOT).as_posix(),
            }
        )
        print(f"Rendered {source_path.name}")

    _remove_stale_samples(used_slugs)
    _update_readme(records)
    print(f"Updated {README.relative_to(ROOT)} with {len(records)} artwork previews")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=68)
    args = parser.parse_args()
    if args.width < 1 or args.height < 1:
        parser.error("--width and --height must be positive")
    try:
        build_gallery(args.input_dir.resolve(), (args.width, args.height))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())